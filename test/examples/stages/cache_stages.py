import curifactory as cf
from curifactory.caching import FileReferenceCacher
import os


@cf.stage(None, ["output_paths"], [FileReferenceCacher])
def filerefcacher_stage_multifile(record):
    file_path = record.get_dir("my_files")
    my_file_list = [os.path.join(file_path, f"thing{num}") for num in range(5)]

    for file_name in my_file_list:
        with open(file_name, "w") as outfile:
            outfile.write("Test file\n")

    # spit out a separate file into the cache to help detect if the stage ran.
    with open(os.path.join(record.manager.cache_path, "stage_ran"), "w") as outfile:
        outfile.write("\n")

    return my_file_list


@cf.stage(None, ["output_path"], [FileReferenceCacher])
def filerefcacher_stage(record):
    file_path = record.get_path("my_file")

    with open(file_path, "w") as outfile:
        outfile.write("Test file\n")

    # spit out a separate file into the cache to help detect if the stage ran.
    with open(os.path.join(record.manager.cache_path, "stage_ran"), "w") as outfile:
        outfile.write("\n")

    return file_path
