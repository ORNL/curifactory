"""Testing the decorators to help orchestrate caching and
input/output passing through record state between stages."""

import copy
import logging
import os
import pickle
import time
from functools import wraps
from typing import Any, Union

import psutil

from curifactory import utils
from curifactory.caching import FileReferenceCacher, Lazy, PickleCacher
from curifactory.record import ArtifactRepresentation, MapArtifactRepresentation, Record

# NOTE: resource only exists on unix systems
if os.name != "nt":
    import resource


class InputSignatureError(Exception):
    pass


class OutputSignatureError(Exception):
    pass


class EmptyCachersError(Exception):
    pass


class ExecutingWithSkippedInputError(Exception):
    pass


class CachersMismatchError(Exception):
    pass


# TODO: this doesn't belong here but not sure where to put it
class SkippedOutput:
    """An object placed into record state when a stage's execution is skipped based
    on the DAG. This is so that the inputs check at the beginning of the stage (prior
    to DAG execution check) does not fail."""

    def __init__(
        self, record: Record, stage_name: str, artifact_rep: ArtifactRepresentation
    ):
        self.artifact = artifact_rep
        self.dag_rep = (record.get_record_index(), stage_name)


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
    inputs: list[str] = None,
    outputs: list[Union[str, Lazy]] = None,
    cachers: list = None,
    suppress_missing_inputs: bool = False,
):
    """Decorator to wrap around a function that represents a single step in an experiment,
    a block with inputs and outputs pertaining to the remainder of that experiment.

    Important:
        Any function wrapped with the stage decorator must take a Record instance as the first
        parameter, followed by the input parameters corresponding to the :code:`inputs` list.

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
            if record.manager.map_mode:
                logging.debug("Mapping stage %s", name)
            else:
                logging.info("-----")
                logging.info("Stage %s", name)
            pre_footprint = 0
            if os.name != "nt":
                pre_footprint = (
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                )
            pre_mem_usage = psutil.Process().memory_info().rss
            if record.manager.stage_active:
                logging.warn(
                    "Stage '%s' executed while another stage ('%s') was already running. Directly executing a stage from another stage is not advised."
                    % (name, record.manager.current_stage_name)
                )
            record.manager.current_stage_name = name
            record.manager.stage_active = True
            record.stages.append(name)
            record.stage_outputs.append([])
            record.stage_inputs.append([])
            record.manager.update_map_progress(record, "start")

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
                    if suppress_missing_inputs and not record.manager.map_mode:
                        logging.warning(
                            "Suppressed missing inputs, will expect function signature default value for '%s' or a direct argument pass on the stage function call..."
                            % function_input
                        )
                        # function_inputs[function_input] = None
                        # NOTE: we don't actually need to pass in None, we can expect the user to implement whatever defaults they want for optional parameters. If they don't specify a default, this will fail as normal.
                    elif function_input not in kwargs and not record.manager.map_mode:
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
                    # set the active record on the cacher as well as provide a default name
                    # (the name of the output)
                    cachers[i].set_record(record)
                    cachers[
                        i
                    ].stage = name  # set current stage name, so get_path is correct in later stages (particularly for lazy)
                    if cachers[i].name is None and cachers[i].path_override is None:
                        if type(outputs[i]) == Lazy:
                            cachers[i].name = outputs[i].name
                        else:
                            cachers[i].name = outputs[i]
            record.stage_cachers = cachers

            # at this point we've grabbed all information we would need if we're
            # just mapping out the stages, so return at this point.
            # TODO: 3/8/2023 - not true, we're not getting outputs
            if record.manager.map_mode:
                record.manager.stage_active = False
                # in order to get a more detailed map that accurately shows input/output names,
                # we need to create pseudo-state-artifact-representations for the outputs. Since
                # we obviously can't add the actual artifacts (there are none without running!),
                # we just add the string key and a name, so record __repr__ has something to use
                _get_output_representations_for_map(record, outputs, cachers, None)
                record.stage_cachers = None
                return record

            # determine if we need to execute this stage and handle any
            # cached values.
            execute_stage = True
            pre_cache_time_start = time.perf_counter()  # time to load from cache
            record.manager.lock()

            # if we have an execution list from our stage DAG, use that
            # to determine if this stage executes or not.
            if record.manager.map is not None:
                stage_rep = (record.get_record_index(), name)
                if stage_rep not in record.manager.map.execution_list:
                    logging.debug('DAG-indicated stage skip "%s".' % str(stage_rep))
                    _dag_skip_check_cached_outputs(name, record, outputs, cachers)

                    # grab any possible previous reportables so they still end up in report.
                    _check_cached_reportables(name, record)
                    record.store_tracked_paths()
                    execute_stage = False
                else:
                    # the representation is in the execution list, so execute!
                    execute_stage = True
            # otherwise, proceed normally with cache and load checks
            else:
                cache_valid = _check_cached_outputs(name, record, outputs, cachers)
                if cache_valid:
                    # get previous reportables if available
                    _check_cached_reportables(name, record)

                    # if we've hit this point, we will be returning early/not executing
                    # the stage because all outputs are found. The process of checking
                    # cached outputs should correctly add all the necessary tracked paths,
                    # so to transfer these paths into a store full run, we just need
                    # the below call
                    # NOTE: I _believe_ that we also get metadata from this because
                    # the load_metadata will have entered the metadata path already.
                    # this will need to be tested
                    record.store_tracked_paths()
                    execute_stage = False
                else:
                    # at least one output wasn't cached, so execute order 66!
                    execute_stage = True

            # check each input for Lazy objects and load them if we know we have to execute this stage
            if execute_stage:
                for function_input in function_inputs:
                    if (
                        type(function_inputs[function_input]) == Lazy
                        and function_inputs[function_input].resolve
                    ):
                        logging.debug(
                            "Resolving lazy load object '%s'" % function_input
                        )
                        function_inputs[function_input] = function_inputs[
                            function_input
                        ].load()
                    # make sure a skipped output hasn't made it through - this would indicate
                    # a mistake in the DAG or perhaps the user didn't correctly list all expected
                    # state inputs in an aggregate
                    if type(function_inputs[function_input]) == SkippedOutput:
                        raise ExecutingWithSkippedInputError(
                            "Input '%s' was never computed, indicating a DAG error. Try running with '--no-map'."
                            % function_input
                        )

            record.manager.unlock()
            pre_cache_time_end = time.perf_counter()
            if not execute_stage:
                post_mem_usage = psutil.Process().memory_info().rss
                post_footprint = 0
                if os.name != "nt":
                    post_footprint = (
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
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
                record.manager.stage_active = False
                record.manager.update_map_progress(record, "continue")
                record.stage_cachers = None
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
            record.store_tracked_paths()
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
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
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
            record.manager.stage_active = False
            record.manager.update_map_progress(record, "continue")
            record.stage_cachers = None
            return record

        return wrapper

    return decorator


def aggregate(  # noqa: C901 -- TODO: will be difficult to simplify...
    expected_state: list[str] = None, outputs: list[str] = None, cachers: list = None
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
        expected_state (list[str]): A list of variable names this stage expects to find in the
            state of each record passed into it. A warning will be thrown on any records that
            do not have the requested variable in state. Variables listed here are used for the
            DAG/map calculation to determine which stages are actually required to run for this
            stage to have everything it needs.
        outputs (list[str]): A list of variable names that this stage will return and store
            in the record state. These represent, in order, the tuple of returned values from
            the function being wrapped.
        cachers (list[Cacheable]): An optional list of Cacheable instances ("strategies") to
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
        def wrapper(record: Record, records: list[Record] = None, **kwargs):
            # set the logging prefix to the args name
            if record.args is not None:
                utils.set_logging_prefix(f"[{record.args.name}] ")
            else:
                utils.set_logging_prefix("")

            if records is None:
                # if no explicit request for a specific set of records given,
                # use all previous records (except own record)
                records = [
                    manager_record
                    for manager_record in record.manager.records
                    if manager_record != record
                ]
            record.input_records = records

            name = function.__name__
            if record.manager.map_mode:
                logging.debug("Mapping aggregate stage %s", name)
            else:
                logging.info("-----")
                logging.info("Stage (aggregate) %s", name)
            pre_footprint = 0
            if os.name != "nt":
                pre_footprint = (
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
                )
            pre_mem_usage = psutil.Process().memory_info().rss
            if record.manager.stage_active:
                logging.warn(
                    "Stage '%s' executed while another stage ('%s') was already running. Directly executing a stage from another stage is not advised."
                    % (name, record.manager.current_stage_name)
                )
            record.manager.current_stage_name = name
            record.set_aggregate(records)
            record.stages.append(name)
            record.stage_outputs.append([])
            record.stage_inputs.append([])
            record.manager.update_map_progress(record, "start")

            # apply consistent handling
            nonlocal expected_state, outputs, cachers
            if expected_state is None:
                expected_state = []
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

            # check for mismatched amounts of cachers
            if cachers is not None and len(cachers) != len(outputs):
                raise CachersMismatchError(
                    f"Stage '{name}' - the number of cachers does not match the number of outputs to cache"
                )

            # similar to how inputs are checked on the state for a regular stage, we use
            # `expected_state` to (softly) check each input record for the requested state
            # variables. We don't actually load/pass anything differently to the function,
            # but this is useful from a documentation and debugging standpoint, and is required
            # for DAG computation to work as expected.
            for expected_input in expected_state:
                for prev_record in records:
                    if expected_input not in prev_record.state_artifact_reps:
                        logging.warning(
                            "Expected state variable '%s' not found in %s"
                            % (expected_input, prev_record.get_reference_name())
                        )
                    else:
                        record.stage_inputs[-1].append(
                            prev_record.state_artifact_reps[expected_input]
                        )

            # see note in stage
            if cachers is not None:
                # instantiate cachers if not already
                for i in range(len(cachers)):
                    cacher = cachers[i]
                    if type(cacher) == type:
                        cachers[i] = cacher()
                    # set the active record on the cacher as well as provide a default name
                    # (the name of the output)
                    cachers[i].set_record(record)
                    cachers[
                        i
                    ].stage = name  # set current stage name, so get_path is correct in later stages (particularly for lazy)
                    if cachers[i].name is None and cachers[i].path_override is None:
                        if type(outputs[i]) == Lazy:
                            cachers[i].name = outputs[i].name
                        else:
                            cachers[i].name = outputs[i]
            record.stage_cachers = cachers

            # at this point we've grabbed all information we would need if we're
            # just mapping out the stages, so return at this point.
            # TODO: 3/8/2023 - not true, we're not getting outputs
            if record.manager.map_mode:
                record.manager.stage_active = False
                # in order to get a more detailed map that accurately shows input/output names,
                # we need to create pseudo-state-artifact-representations for the outputs. Since
                # we obviously can't add the actual artifacts (there are none without running!),
                # we just add the string key and a name, so record __repr__ has something to use
                _get_output_representations_for_map(record, outputs, cachers, records)
                record.stage_cachers = None
                return record

            # determine if we need to execute this stage and handle any
            # cached values.
            execute_stage = True
            pre_cache_time_start = time.perf_counter()  # time to load from cache
            record.manager.lock()

            # if we have an execution list from our stage DAG, use that
            # to determine if this stage executes or not.
            if record.manager.map is not None:
                stage_rep = (record.get_record_index(), name)
                if stage_rep not in record.manager.map.execution_list:
                    logging.debug('DAG-indicated stage skip "%s".' % str(stage_rep))
                    _dag_skip_check_cached_outputs(
                        name, record, outputs, cachers, records
                    )

                    # grab any possible previous reportables so they still end up in report.
                    _check_cached_reportables(name, record)
                    record.store_tracked_paths()
                    execute_stage = False
                else:
                    # the representation is in the execution list, so execute!
                    execute_stage = True
            # otherwise, proceed normally with cache and load checks
            else:
                cache_valid = _check_cached_outputs(
                    name, record, outputs, cachers, records
                )
                if cache_valid:
                    # get previous reportables if available
                    _check_cached_reportables(name, record, records)

                    # if we've hit this point, we will be returning early/not executing
                    # the stage because all outputs are found. The process of checking
                    # cached outputs should correctly add all the necessary tracked paths,
                    # so to transfer these paths into a store full run, we just need
                    # the below call
                    # NOTE: I _believe_ that we also get metadata from this because
                    # the load_metadata will have entered the metadata path already.
                    # this will need to be tested
                    record.store_tracked_paths()
                    execute_stage = False
                else:
                    # at least one output wasn't cached, so execute order 66!
                    execute_stage = True

            record.manager.unlock()
            pre_cache_time_end = time.perf_counter()

            if not execute_stage:
                post_mem_usage = psutil.Process().memory_info().rss
                post_footprint = 0
                if os.name != "nt":
                    post_footprint = (
                        resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
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
                record.manager.stage_active = False
                record.manager.update_map_progress(record, "continue")
                record.stage_cachers = None
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
            record.store_tracked_paths()
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
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
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
            record.manager.stage_active = False
            record.manager.update_map_progress(record, "continue")
            record.stage_cachers = None
            return record

        return wrapper

    return decorator


def _get_output_representations_for_map(
    record, outputs: list[str], cachers, records=None
) -> list[MapArtifactRepresentation]:
    """Check if the requested outputs are cached but do not load them, simply return
    a list of statuses for found."""
    if cachers == []:
        raise EmptyCachersError(
            "Do not use '[]' for cachers. This will always short-circuit because there is nothing that isn't cached."
        )

    artifacts = []
    for i in range(len(outputs)):
        metadata = None
        cacher = None
        is_cached = False
        if cachers is not None:
            cacher = cachers[i]
            is_cached = cacher.check()
            if is_cached:
                metadata = cacher.load_metadata()
        artifact = _add_output_artifact(
            record, None, outputs, i, metadata, cacher, is_cached
        )
        artifacts.append(artifact)

    return artifacts


def _dag_skip_check_cached_outputs(
    stage_name: str, record, outputs: list[str], cachers, records=None
):
    """Checks for cached values and loads any relevant metadata into artifact representations.
    This function does not actually load values themselves, meant to be called for a skipped stage
    in dag-based execution."""
    if cachers == []:
        raise EmptyCachersError(
            "Do not use '[]' for cachers. This will always short-circuit because there is nothing that isn't cached."
        )

    skipped_function_outputs = []
    for i, output_name in enumerate(outputs):
        logging.debug("Checking cache status (not loading into memory.)")

        cacher = None
        metadata = None
        is_cached = False
        output = None
        if cachers is not None:
            if cachers[i].check():
                cachers[i].load_metadata()
                if type(outputs[i]) == Lazy:
                    outputs[i].cacher = cachers[i]
                    # we set the output to just be the Lazy instance for now
                    output = outputs[i]
                else:
                    # TODO: make a lazy for it anyway? Evnetually use ref instead
                    output = Lazy(output_name)
                    output.cacher = cachers[i]

                cacher = cachers[i]
                metadata = cachers[i].metadata
                is_cached = True
        artifact = _add_output_artifact(
            record, None, outputs, i, metadata, cacher, is_cached
        )
        if is_cached:
            artifact.file = cachers[i].get_path()
        # add a skippedoutput instance if it's not a cached value
        if output is None:
            output = SkippedOutput(record, stage_name, artifact)
        skipped_function_outputs.append(output)
        record.state[str(outputs[i])] = output


def _check_cached_outputs(
    stage_name: str, record, outputs: list[str], cachers, records=None
) -> bool:
    """Check if the requested outputs are cached and load them if so."""
    if cachers == []:
        raise EmptyCachersError(
            "Do not use '[]' for cachers. This will always short-circuit because there is nothing that isn't cached."
        )

    cache_valid = False
    if cachers is not None:
        # NOTE: we put this here because the cachers still need to be set up
        if stage_name in record.manager.overwrite_stages or record.manager.overwrite:
            return False

        # check the cache (and load into record if found)
        cache_valid = True
        function_outputs = []
        for i in range(len(cachers)):
            if cachers[i].check():
                # handle lazy objects by setting the cacher but not actually loading yet.
                if type(outputs[i]) == Lazy:
                    outputs[i].cacher = cachers[i]
                    # we set the output to just be the Lazy instance for now
                    output = outputs[i]
                else:
                    output = cachers[i].load()
                cachers[i].load_metadata()

                function_outputs.append(output)
                record.state[str(outputs[i])] = output

                artifact = _add_output_artifact(
                    record,
                    output,
                    outputs,
                    i,
                    metadata=cachers[i].metadata,
                    cacher=cachers[i],
                    is_cached=True,
                )
                # TODO: (3/21/2023) possibly have "files" which would be cachers.cached_files?
                artifact.file = cachers[i].get_path()
            else:
                # we found something that wasn't cached, recompute everything
                cache_valid = False
                break

        # if we have the cached objects, return them right away
        if cache_valid:
            if len(cachers) == 1:
                record.output = function_outputs[0]
            else:
                record.output = tuple(function_outputs)

    return cache_valid


def _add_output_artifact(
    record,
    object: Any,
    outputs: list[str],
    index: int,
    metadata=None,
    cacher=None,
    is_cached=False,
):
    """Manage representation recording - this creates an artifact representation and adds to the manager's artifacts."""
    if not record.manager.map_mode:
        artifact = ArtifactRepresentation(
            record, outputs[index], object, metadata=metadata, cacher=cacher
        )
    else:
        artifact = MapArtifactRepresentation(
            # NOTE: we don't use map=True for the get record index because we're still in map mode...
            # this should probably change at some point, where getindex also takes the current map_mode
            # into account
            record.get_record_index(),
            record.manager.current_stage_name,
            outputs[index],
            is_cached,
            metadata,
            cacher,
        )
    new_index = len(record.manager.artifacts)
    record.manager.artifacts.append(artifact)
    # if new_index not in record.stage_outputs[-1]:
    record.stage_outputs[-1].append(new_index)
    record.state_artifact_reps[str(outputs[index])] = new_index
    return artifact


def _check_cached_reportables(stage_name, record, aggregate_records=None):
    reportables_list_cacher = FileReferenceCacher(
        name="reportables_file_list", record=record
    )
    if reportables_list_cacher.check():
        reportables_list_cacher.load_metadata()
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

    # pickle each one and store it.
    paths = []
    reportables_path = record.get_dir(
        "reportables"
    )  # this will make sure all reportables go to full store
    for reportable in reportables:
        # make a copy of the reportable without the record, because that seems to break the mp.lock
        # when in parallel mode.
        # NOTE: do NOT use a deepcopy below, runs into same issue.
        reportable_copy = copy.copy(reportable)
        reportable_copy.record = None
        reportable_path = os.path.join(
            reportables_path, f"{reportable.qualified_name}.pkl"
        )
        paths.append(reportable_path)
        logging.debug("Caching reportable '%s'" % reportable_path)
        with open(reportable_path, "wb") as outfile:
            pickle.dump(reportable_copy, outfile)

    # write a cache file out containing the reportables path names.
    reportables_list_cacher = FileReferenceCacher(
        name="reportables_file_list", record=record
    )
    reportables_list_cacher.save(paths)

    # send along metadata for it, to track when the reportables were generated.
    # NOTE: we've already collected_metadata from passing record in init up above,
    # so we don't need to use the extra_metadata field on the cacher.
    reportables_list_cacher.metadata["extra"]["reportables"] = True
    reportables_list_cacher.save_metadata()


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
                f"Caching {outputs[index]} to '{cachers[index].get_path()}'..."
            )
            cachers[index].save(output)
            artifact.file = cachers[index].get_path()

            # generate and save metadata
            # note that if we got to this point, we actually ran the stage code, so
            # we generate _new_ metadata
            cachers[index].collect_metadata()
            cachers[index].metadata["preview"] = artifact.string
            metadata = cachers[index].save_metadata()
            artifact.metadata = metadata

        # if specified as lazy, be sure to populate the cacher
        if type(outputs[index]) == Lazy:
            outputs[index].cacher = cachers[index]
