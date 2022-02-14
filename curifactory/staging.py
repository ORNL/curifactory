"""Testing the decorators to help orchestrate caching and
input/output passing through record state between stages."""

import copy
import logging
import os
import pickle
import psutil

import shutil
import time
from typing import List, Union
from functools import wraps

from curifactory.record import Record, ArtifactRepresentation
from curifactory.caching import Lazy, PickleCacher, FileReferenceCacher
from curifactory import utils


# NOTE: resource only exists on unix systems
if os.name != "nt":
    import resource


class InputSignatureError(Exception):
    pass


class OutputSignatureError(Exception):
    pass


class EmptyCachersError(Exception):
    pass


class CachersMismatchError(Exception):
    pass


def _log_stats(
    record,
    pre_cache_time_start,
    pre_cache_time_end,
    pre_mem_usage,
    post_mem_usage,
    exec_time_start=0,
    exec_time_end=0,
    post_cache_time_start=0,
    post_cache_time_end=0,
    pre_max_footprint=0,
    post_max_footprint=0,
):

    pre_cache_time = pre_cache_time_end - pre_cache_time_start
    exec_time = exec_time_end - exec_time_start
    post_cache_time = post_cache_time_end - post_cache_time_start
    cache_time = pre_cache_time + post_cache_time

    mem_change = post_mem_usage - pre_mem_usage

    footprint_change = post_max_footprint - pre_max_footprint

    # TODO: total_time =

    logging.debug(
        "Memory (current usage/max allocated) - %s / %s"
        % (
            utils.human_readable_mem_usage(post_mem_usage),
            utils.human_readable_mem_usage(post_max_footprint),
        )
    )
    logging.debug(
        "Stage memory impact (current/max) - %s / %s"
        % (
            utils.human_readable_mem_usage(mem_change),
            utils.human_readable_mem_usage(footprint_change),
        )
    )
    logging.debug(
        "Timing - execution: %s  caching: %s"
        % (utils.human_readable_time(exec_time), utils.human_readable_time(cache_time))
    )


def stage(  # noqa: C901 -- TODO: will be difficult to simplify...
    inputs: List[str] = None,
    outputs: List[Union[str, Lazy]] = None,
    cachers: List = None,
    suppress_missing_inputs: bool = False,
):
    """Decorator to wrap around a function that represents a single step in an experiment,
    a block with inputs and outputs pertaining to the remainder of that experiment.

    Important:
        Any function wrapped with the stage decorator must take a Record instance as the first
        parameter, followed by the input parameters corresponding to the :code:`inputs` list.

    Note:
        Note that a wrapped function that successfully finds all cached outputs does not
        execute, meaning any reportables that might have been output to the experiment report
        **will not run.** This can be mitigated by putting relevant reportables in a separate
        stage that does not cache anything. This note similarly applies to any other "side effects"
        that might result from stage code execution. Careful design of stages should ensure
        that the effects of stage functions are limited exclusively to the given inputs and
        returned outputs.

    Args:
        inputs (List[str]): A list of variable names that this stage will need from the
            record state. **Note that all inputs listed here must have a corresponding
            input parameter in the function definition line, each with the exact same name
            as in this list.**
        outputs (List[Union[str, Lazy]]): A list of variable names that this stage will return and store
            in the record state. These represent, in order, the tuple of returned values from
            the function being wrapped.
        cachers (List[Cacheable]): An optional list of Cacheable instances ("strategies") to
            apply to each of the return outputs. If specified, for each output, an instance
            of the corresponding cacher is initialized, and the :code:`save()` function is called.
            Before the wrapped function is called, the output path is first checked, and if it
            exists and the current record args are not set to overwrite, the :code:`load()` function
            is called and the wrapped function **does not execute.** Note that caching is all
            or nothing for a single function, you cannot cache only one returned value out of
            several.
        suppress_missing_inputs (bool): If true, any stage inputs that are not found in the record's
            state will be passed in as :code:`None` rather than raising an exception. This can
            be used to make all inputs optional, such as if a stage will be used after different
            sets of previous stages and not all values are necessarily required.

    Example:
        .. code-block:: python

            @stage(inputs=["data", "model"], outputs=["results"], cachers=[JsonCacher])
            def test_model(record: Record, data: pd.DataFrame, model):
                # ...
                return results_dictionary

        Note that from this example, this stage assumes some other stages have output
        :code:`"data"` and :code:`"model"` at some point.
    """

    def decorator(function):
        @wraps(function)
        def wrapper(record: Record, *args, **kwargs):
            # set the logging prefix to the args name
            if record.args is not None:
                utils.set_logging_prefix(f"[{record.args.name}] ")
            else:
                utils.set_logging_prefix("")

            name = function.__name__
            logging.info("-----")
            logging.info("Stage %s", name)
            pre_footprint = 0
            if os.name != "nt":
                pre_footprint = (
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                )
            pre_mem_usage = psutil.Process().memory_info().rss
            record.manager.current_stage_name = name
            record.stages.append(name)
            record.stage_outputs.append([])
            record.stage_inputs.append([])

            # apply consistent handling
            nonlocal inputs, outputs, cachers
            if inputs is None:
                inputs = []
            if outputs is None:
                outputs = []

            # check for lazy object / cacher mismatch in outputs
            for output in outputs:
                if (
                    type(output) == Lazy
                    and cachers is None
                    and not record.manager.lazy
                    and not record.manager.ignore_lazy
                ):
                    raise OutputSignatureError(
                        "Stage outputs for '%s' contain Lazy objects but do not have cachers specified. Please provide cachers for this stage."
                        % name
                    )

            # replace any non-lazy outputs with lazy or vice-versa depending on manager flags.
            if record.manager.lazy:
                no_cachers = False
                for index, output in enumerate(outputs):
                    if type(output) != Lazy:
                        logging.debug("Forcing lazy cache for '%s'" % output)
                        outputs[index] = Lazy(output)
                        # NOTE: since Lazy caching doesn't work without a cacher, we need to ensure
                        # one if none exists. Pickle is pretty broad, but obviously there are some things
                        # that don't work, so we need to warn about this
                        if cachers is None:
                            no_cachers = True
                            logging.warning(
                                "Stage %s does not have cachers specified, a --lazy run will force caching by applying PickleCachers to anything with none specified, but this can potentially cause errors."
                                % name
                            )
                            cachers = []
                        if no_cachers:
                            cachers.append(PickleCacher)
            elif record.manager.ignore_lazy:
                for index, output in enumerate(outputs):
                    if type(output) == Lazy:
                        logging.debug("Disabling lazy cache for '%s'" % output)
                        outputs[index] = output.name

            # check for mismatched amounts of cachers
            if cachers is not None and len(cachers) != len(outputs):
                raise CachersMismatchError(
                    f"Stage '{name}' - the number of cachers does not match the number of outputs to cache."
                )

            # find any required inputs for the function in the record
            # NOTE: this is before checking cache so that we can keep a record of what inputs we're expecting
            # (for mapping purposes)
            # note that we turn off lazy resolution because we haven't yet
            # determined if the stage even needs to run yet or not. We handle
            # resolution manually farther down.
            record.state.resolve = False
            function_inputs = {}
            for function_input in inputs:
                # NOTE: this means the state was probably manually changed
                if function_input not in record.state_artifact_reps:
                    record.stage_inputs[-1].append(-1)
                else:
                    record.stage_inputs[-1].append(
                        record.state_artifact_reps[function_input]
                    )
                # TODO: add None if function_input is not in state. (There are a few cases
                # where this shouldn't be a problem, e.g. if everything is cached but a new
                # input was added - this shouldn't inherently cause a problem unless the
                # output would be wrong.
                if function_input not in record.state:
                    if suppress_missing_inputs:
                        logging.warning(
                            "Suppressed missing inputs, will expect function signature default value for '%s' or a direct argument pass on the stage function call..."
                            % function_input
                        )
                        # function_inputs[function_input] = None
                        # NOTE: we don't actually need to pass in None, we can expect the user to implement whatever defaults they want for optional parameters. If they don't specify a default, this will fail as normal.
                    elif function_input not in kwargs:
                        raise KeyError(
                            "Stage '%s' input '%s' not found in record state and not passed to function call. Set 'suppress_missing_inputs=True' on the stage and give a default value in the function signature if this should run anyway."
                            % (name, function_input)
                        )
                else:
                    # # check for a lazy object and resolve it if so
                    # if type(record.state[function_input]) == Lazy:
                    #     # TODO: no no no don't do this here, we haven't checked for cached outputs yet.
                    #     logging.debug("Resolving lazy load object '%s'" % function_input)
                    #     function_inputs[function_input] = record.state[function_input].load()
                    # else:
                    #     # otherwise we just directly pull it from the record state.
                    function_inputs[function_input] = record.state[function_input]
            function_inputs.update(kwargs)
            record.state.resolve = True

            # note to future self and anyone else who's IDE says this is repeated code (with aggregate below)
            # no, you cannot abstract this into _check_cached_outputs - if you try to reassign to cachers from
            # another function, because of the deep voodoo black magic sorcery that is decorators with arguments,
            # it considers it different code.
            if cachers is not None:
                # instantiate cachers if not already
                for i in range(len(cachers)):
                    cacher = cachers[i]
                    if type(cacher) == type:
                        cachers[i] = cacher()
                    # set the active record on the cacher
                    cachers[i].record = record

            # check for cached outputs and lazy load inputs if needed
            pre_cache_time_start = time.perf_counter()  # time to load from cache
            record.manager.lock()
            cache_valid = _check_cached_outputs(name, record, outputs, cachers)
            if cache_valid:
                # get previous reportables if available
                _check_cached_reportables(name, record)

            # check each input for Lazy objects and load them if we know we have to execute this stage
            if not cache_valid:
                for function_input in function_inputs:
                    if type(function_inputs[function_input]) == Lazy:
                        logging.debug(
                            "Resolving lazy load object '%s'" % function_input
                        )
                        function_inputs[function_input] = function_inputs[
                            function_input
                        ].load()

            record.manager.unlock()
            pre_cache_time_end = time.perf_counter()
            if cache_valid:
                post_mem_usage = psutil.Process().memory_info().rss
                post_footprint = 0
                if os.name != "nt":
                    post_footprint = (
                        resource.getrusage(resource.RUSAGE_THREAD).ru_maxrss * 1024
                    )
                _log_stats(
                    record,
                    pre_cache_time_start,
                    pre_cache_time_end,
                    pre_mem_usage,
                    post_mem_usage,
                    0,
                    0,
                    0,
                    0,
                    pre_footprint,
                    post_footprint,
                )
                utils.set_logging_prefix("")
                return record

            # run the function
            logging.info("Stage %s executing...", name)
            exec_time_start = time.perf_counter()
            try:
                function_outputs = function(record, *args, **function_inputs)
            except TypeError as e:
                raise InputSignatureError(
                    "Signature for '%s' does not match stage input list. Signature should include %s, or there may be missing default values for a stage called with suppress_missing_inputs. Sub error: %s"
                    % (name, str(inputs), str(e))
                )
            exec_time_end = time.perf_counter()

            # handle storing outputs in record
            post_cache_time_start = time.perf_counter()
            record.manager.lock()
            _store_outputs(name, record, outputs, cachers, function_outputs)
            _store_reportables(name, record)
            record.manager.unlock()
            post_cache_time_end = time.perf_counter()

            # free up any memory from cached things
            cleaned_function_outputs = []
            lazy_found = False

            # iterate the outputs rather than function_outputs
            for index, output_name in enumerate(outputs):
                if type(output_name) == Lazy:
                    lazy_found = True
                    logging.debug("Lazy object '%s' will be cleaned." % output_name)
                    if index == 0 and len(outputs) == 1:
                        cleaned_function_outputs = outputs[
                            index
                        ]  # so that this doesn't syntactically read output_name, because it's Lazy not a str
                    else:
                        cleaned_function_outputs.append(outputs[index])
                else:
                    if index == 0 and len(outputs) == 1:
                        cleaned_function_outputs = function_outputs
                    else:
                        cleaned_function_outputs.append(function_outputs[index])
            if len(outputs) > 1:
                cleaned_function_outputs = tuple(cleaned_function_outputs)

            # free up any lazy cache objects
            if lazy_found:
                logging.debug("Freeing memory from lazy objects...")
                pre_del_mem_usage = psutil.Process().memory_info().rss
                del function_outputs
                post_del_mem_usage = psutil.Process().memory_info().rss
                del_mem_diff = pre_del_mem_usage - post_del_mem_usage
                logging.debug("Freed %s" % utils.human_readable_mem_usage(del_mem_diff))

            logging.info("Stage %s complete", name)

            # check memory usage
            post_footprint = 0
            if os.name != "nt":
                post_footprint = (
                    resource.getrusage(resource.RUSAGE_THREAD).ru_maxrss * 1024
                )
            post_mem_usage = psutil.Process().memory_info().rss

            _log_stats(
                record,
                pre_cache_time_start,
                pre_cache_time_end,
                pre_mem_usage,
                post_mem_usage,
                exec_time_start,
                exec_time_end,
                post_cache_time_start,
                post_cache_time_end,
                pre_footprint,
                post_footprint,
            )

            record.output = cleaned_function_outputs
            utils.set_logging_prefix("")
            return record

        return wrapper

    return decorator


def aggregate(  # noqa: C901 -- TODO: will be difficult to simplify...
    outputs: List[str] = None, cachers: List = None
):
    """Decorator to wrap around a function that represents some step that must operate across
    multiple different argsets or "experiment lines" within an experiment. This is normally
    used to run final analyses and comparisons of results across all passed argument sets.

    Important:
        Any function wrapped with the aggregate decorator must take a Record instance as the first
        parameter and a list of Record instances as the second. The former is the record that applies
        to this function, and the latter is the set of other records from elsewhere in the experiment
        that this function needs to aggregate across.

    Args:
        outputs (List[str]): A list of variable names that this stage will return and store
            in the record state. These represent, in order, the tuple of returned values from
            the function being wrapped.
        cachers (List[Cacheable]): An optional list of Cacheable instances ("strategies") to
            apply to each of the return outputs. If specified, for each output, an instance
            of the corresponding cacher is initialized, and the :code:`save()` function is called.
            Before the wrapped function is called, the output path is first checked, and if it
            exists and the current record args are not set to overwrite, the :code:`load()` function
            is called and the wrapped function **does not execute.** Note that caching is all
            or nothing for a single function, you cannot cache only one returned value out of
            several.


    Example:
        .. code-block:: python

            @aggregate(["final_results"], [JsonCacher])
            def compile_results(record: Record, records: List[Record]):
                results = {}
                for prev_record in records:
                    results[prev_record.args.name] = prev_record.state["results"]
                return results
    """

    def decorator(function):
        @wraps(function)
        def wrapper(record: Record, records: List[Record] = None, **kwargs):
            # set the logging prefix to the args name
            if record.args is not None:
                utils.set_logging_prefix(f"[{record.args.name}] ")
            else:
                utils.set_logging_prefix("")

            name = function.__name__
            logging.info("-----")
            logging.info("Stage (aggregate) %s", name)
            pre_footprint = 0
            if os.name != "nt":
                pre_footprint = (
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                )
            pre_mem_usage = psutil.Process().memory_info().rss
            record.manager.current_stage_name = name
            record.stages.append(name)
            record.stage_outputs.append([])
            record.stage_inputs.append([])

            # apply consistent handling
            nonlocal outputs, cachers
            if outputs is None:
                outputs = []

            # check for lazy object / cacher mismatch in outputs
            for output in outputs:
                if (
                    type(output) == Lazy
                    and cachers is None
                    and not record.manager.lazy
                    and not record.manager.ignore_lazy
                ):
                    raise OutputSignatureError(
                        "Stage outputs for '%s' contain Lazy objects but do not have cachers specified. Please provide cachers for this stage."
                        % name
                    )

            # replace any non-lazy outputs with lazy or vice-versa depending on manager flags.
            if record.manager.lazy:
                no_cachers = False
                for index, output in enumerate(outputs):
                    if type(output) != Lazy:
                        logging.debug("Forcing lazy cache for '%s'" % output)
                        outputs[index] = Lazy(output)
                        # NOTE: since Lazy caching doesn't work without a cacher, we need to ensure
                        # one if none exists. Pickle is pretty broad, but obviously there are some things
                        # that don't work, so we need to warn about this
                        if cachers is None:
                            no_cachers = True
                            logging.warning(
                                "Aggregate stage %s does not have cachers specified, a --lazy run will force caching by applying PickleCachers to anything with none specified, but this can potentially cause errors."
                                % name
                            )
                            cachers = []
                        if no_cachers:
                            cachers.append(PickleCacher)
            elif record.manager.ignore_lazy:
                for index, output in enumerate(outputs):
                    if type(output) == Lazy:
                        logging.debug("Disabling lazy cache for '%s'" % output)
                        outputs[index] = output.name

            if records is None:
                # if no explicit request for a specific set of records given,
                # use all previous records
                records = record.manager.records
            record.input_records = records

            if cachers is not None and len(cachers) != len(outputs):
                raise CachersMismatchError(
                    f"Stage '{name}' - the number of cachers does not match the number of outputs to cache"
                )

            # see note in stage
            if cachers is not None:
                # instantiate cachers if not already
                for i in range(len(cachers)):
                    cacher = cachers[i]
                    if type(cacher) == type:
                        cachers[i] = cacher()
                    # set the active record on the cacher
                    cachers[i].record = record

            pre_cache_time_start = time.perf_counter()  # time to load from cache
            record.manager.lock()
            cache_valid = _check_cached_outputs(name, record, outputs, cachers, records)
            if cache_valid:
                # get previous reportables if available
                _check_cached_reportables(name, record, records)
            record.manager.unlock()
            pre_cache_time_end = time.perf_counter()

            if cache_valid:
                post_mem_usage = psutil.Process().memory_info().rss
                post_footprint = 0
                if os.name != "nt":
                    post_footprint = (
                        resource.getrusage(resource.RUSAGE_THREAD).ru_maxrss * 1024
                    )
                _log_stats(
                    record,
                    pre_cache_time_start,
                    pre_cache_time_end,
                    pre_mem_usage,
                    post_mem_usage,
                    0,
                    0,
                    0,
                    0,
                    pre_footprint,
                    post_footprint,
                )
                utils.set_logging_prefix("")
                return record

            # run the function
            logging.info("Stage (aggregate) %s executing...", name)
            exec_time_start = time.perf_counter()
            # NOTE: passing additional args to an aggregate stage is sort of undefined functionality,
            # this probably should be discouraged.
            function_outputs = function(record, records, **kwargs)
            exec_time_end = time.perf_counter()

            # handle storing outputs in record
            post_cache_time_start = time.perf_counter()
            record.manager.lock()
            _store_outputs(name, record, outputs, cachers, function_outputs, records)
            _store_reportables(name, record, records)
            record.manager.unlock()
            post_cache_time_end = time.perf_counter()

            # free up any memory from cached things
            cleaned_function_outputs = []
            lazy_found = False

            # iterate the outputs rather than function_outputs
            for index, output_name in enumerate(outputs):
                if type(output_name) == Lazy:
                    lazy_found = True
                    logging.debug("Lazy object '%s' will be cleaned." % output_name)
                    if index == 0 and len(outputs) == 1:
                        cleaned_function_outputs = outputs[
                            index
                        ]  # so that this doesn't syntactically read output_name, because it's Lazy not a str
                    else:
                        cleaned_function_outputs.append(outputs[index])
                else:
                    if index == 0 and len(outputs) == 1:
                        cleaned_function_outputs = function_outputs
                    else:
                        cleaned_function_outputs.append(function_outputs[index])
            if len(outputs) > 1:
                cleaned_function_outputs = tuple(cleaned_function_outputs)

            # free up any lazy cache objects
            if lazy_found:
                logging.debug("Freeing memory from lazy objects...")
                pre_del_mem_usage = psutil.Process().memory_info().rss
                del function_outputs
                post_del_mem_usage = psutil.Process().memory_info().rss
                del_mem_diff = pre_del_mem_usage - post_del_mem_usage
                logging.debug("Freed %s" % utils.human_readable_mem_usage(del_mem_diff))

            logging.info("Stage (aggregate) %s complete", name)

            # check memory usage
            post_footprint = 0
            if os.name != "nt":
                post_footprint = (
                    resource.getrusage(resource.RUSAGE_THREAD).ru_maxrss * 1024
                )
            post_mem_usage = psutil.Process().memory_info().rss

            _log_stats(
                record,
                pre_cache_time_start,
                pre_cache_time_end,
                pre_mem_usage,
                post_mem_usage,
                exec_time_start,
                exec_time_end,
                post_cache_time_start,
                post_cache_time_end,
                pre_footprint,
                post_footprint,
            )

            record.output = cleaned_function_outputs
            utils.set_logging_prefix("")
            return record

        return wrapper

    return decorator


def _check_cached_outputs(stage_name, record, outputs, cachers, records=None):
    if cachers == []:
        raise EmptyCachersError(
            "Do not use '[]' for cachers. This will always short-circuit because there is nothing that isn't cached."
        )

    cache_valid = False
    if cachers is not None:
        # set the path for every instantiated cacher
        paths = []
        for index, arg in enumerate(outputs):
            if cachers[index].path_override is None:
                # the str(arg) will handle Lazy objects
                path = record.manager.get_path(
                    str(arg), record, aggregate_records=records
                )
            elif str.endswith(cachers[index].extension, cachers[index].path_override):
                # if the path override includes the extension they provided a full file name
                # NOTE: this is useful if there's a static file that won't change across diff
                # runs or paramsets, like an input dataset
                path = cachers[index].path
            else:
                path = record.manager.get_path(
                    arg,
                    record,
                    base_path=cachers[index].path,
                    aggregate_records=records,
                )
            path = cachers[index].set_path(path)
            paths.append(path)

        # NOTE: we put this here because the cachers still need to be set up
        if stage_name in record.manager.overwrite_stages or record.manager.overwrite:
            return False

        # check the cache (and load into record if found)
        cache_valid = True
        function_outputs = []
        for i in range(len(paths)):
            if cachers[i].check():

                # handle lazy objects by setting the cacher but not actually loading yet.
                if type(outputs[i]) == Lazy:
                    outputs[i].cacher = cachers[i]
                    # we set the output to just be the Lazy instance for now
                    output = outputs[i]
                else:
                    output = cachers[i].load()
                function_outputs.append(output)
                record.state[str(outputs[i])] = output

                artifact = _add_output_artifact(record, output, outputs, i)
                artifact.file = cachers[i].path

                # copy it over to output run folder if necessary
                if record.manager.store_entire_run:
                    # if we don't handle lazy separately it will literally store the lazy object.
                    # Instead, just use the OS to copy the file over. (This avoids us having to
                    # eat the memory costs of reloading and resaving.)
                    previous_path = cachers[i].path
                    cachers[i].set_path(
                        record.manager.get_path(
                            outputs[i], record, output=True, aggregate_records=records
                        )
                    )
                    if type(outputs[i]) == Lazy:
                        shutil.copyfile(previous_path, cachers[i].path)
                    else:
                        cachers[i].save(output)
            else:
                # we found something that wasn't cached, recompute everything
                cache_valid = False
                break

        # if we have the cached objects, return them right away
        if cache_valid:
            if len(paths) == 1:
                record.output = function_outputs[0]
            else:
                record.output = tuple(function_outputs)
            # return record

    return cache_valid


def _add_output_artifact(record, object, outputs, index):
    """manage representation recording"""
    artifact = ArtifactRepresentation(record, outputs[index], object)
    new_index = len(record.manager.artifacts)
    record.manager.artifacts.append(artifact)
    # if new_index not in record.stage_outputs[-1]:
    record.stage_outputs[-1].append(new_index)
    record.state_artifact_reps[str(outputs[index])] = new_index
    return artifact


def _check_cached_reportables(stage_name, record, aggregate_records=None):
    reportables_list_cacher = FileReferenceCacher()
    reportables_list_cacher.record = record
    reportables_list_cacher.set_path(
        record.manager.get_path(
            "reportables_file_list", record, aggregate_records=aggregate_records
        )
    )
    if reportables_list_cacher.check():
        paths = reportables_list_cacher.load()
        for path in paths:
            with open(path, "rb") as infile:
                logging.debug("Reusing cached reportable '%s'" % path)
                reportable = pickle.load(infile)
                record.report(reportable)
        return True
    # the return of this function is simply used to determine if we need to store again?
    return False


def _store_reportables(stage_name, record, aggregate_records=None):
    # get all reportables from the manager for this record and stage name
    reportables = []
    for reportable in record.manager.reportables:
        if reportable.record == record and reportable.stage == stage_name:
            reportables.append(reportable)

    if len(reportables) == 0:
        return

    # pickle each one and store it. (we'll have to handle store-full the same way as outputs below I think)
    # TODO: (02/10/2022) like record get_dir and get_path normally, _this does not transfer into a store-full
    # run.
    paths = []
    reportables_path = record.get_dir("reportables")
    for reportable in reportables:
        # make a copy of the reportable without the record, because that seems to break the mp.lock
        # when in parallel mode.
        # NOTE: do NOT use a deepcopy below, runs into same issue.
        reportable_copy = copy.copy(reportable)
        reportable_copy.record = None
        reportable_path = os.path.join(reportables_path, f"{reportable.name}.pkl")
        paths.append(reportable_path)
        logging.debug("Caching reportable '%s'" % reportable_path)
        with open(reportable_path, "wb") as outfile:
            pickle.dump(reportable_copy, outfile)

    # write a cache file out containing the reportables path names. This is a...file reference cacher...can we re-use the logic?
    reportables_list_cacher = FileReferenceCacher()
    reportables_list_cacher.record = record
    reportables_list_cacher.set_path(
        record.manager.get_path(
            "reportables_file_list", record, aggregate_records=aggregate_records
        )
    )
    reportables_list_cacher.save(paths)
    # NOTE: unnecessary because the reportables don't get copied over anyway, see todo note above.
    # (we should get this for free without needing this code when we add extra path tracking to the manager.)
    # if record.manager.store_entire_run:
    #     reportables_list_cacher.set_path(
    #         record.manager.get_path(
    #             "reportables_file_list",
    #             record,
    #             output=True,
    #             aggregate_records=aggregate_records,
    #         )
    #     )
    # reportables_list_cacher.save(reportables_path)


def _store_outputs(
    function_name, record, outputs, cachers, function_outputs, records=None
):
    if len(outputs) == 0:
        return

    if cachers is not None:
        logging.info("Stage %s caching outputs..." % function_name)

    if type(function_outputs) != tuple:
        function_outputs = (function_outputs,)

    if len(outputs) != len(function_outputs):
        raise OutputSignatureError(
            "Returned values from '%s' do not match expected stage outputs. The function should return values for %s"
            % (function_name, str(outputs))
        )

    # store each argument in the record and cache if requested
    for index, output in enumerate(function_outputs):
        if type(outputs[index]) == Lazy:
            record.state[str(outputs[index])] = outputs[index]
            # TODO: (01/13/2022) if cachers is none, throw an error
        else:
            record.state[str(outputs[index])] = output

        # manage representation recording
        artifact = _add_output_artifact(record, output, outputs, index)
        if (
            cachers is not None
            and not record.manager.dry
            and not record.manager.dry_cache
        ):
            logging.debug(
                "Caching %s to '%s'..." % (outputs[index], cachers[index].path)
            )
            cachers[index].save(output)
            artifact.file = cachers[index].path

            # check if we store an additional run output copy
            if record.manager.store_entire_run:
                cachers[index].set_path(
                    record.manager.get_path(
                        outputs[index], record, output=True, aggregate_records=records
                    )
                )
                logging.debug(
                    "Caching %s to '%s'..." % (outputs[index], cachers[index].path)
                )
                cachers[index].save(output)

        # if specified as lazy, be sure to populate the cacher
        if type(outputs[index]) == Lazy:
            outputs[index].cacher = cachers[index]
