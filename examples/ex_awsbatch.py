import argparse
import os
import subprocess as sp
import sys

from cosmos.api import Cosmos


def get_instance_info(out_s3_uri, sleep=0):
    return f"""
    df -h > df.txt
    aws s3 cp df.txt {out_s3_uri}

    sleep {sleep}
    """


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument(
        "-i",
        "--container-image",
        help="you must have the aws command line tools installed, and it must have access to copy from the s3 bucket "
        "defined in --s3-prefix-for-command-script-temp-files (ie the container should be able to run "
        "`s3 cp s3://bucket ./`",
        required=True,
    )
    p.add_argument(
        "-b",
        "--s3-prefix-for-command-script-temp-files",
        help="Bucket to use for storing command scripts as temporary files, ex: s3://my-bucket/cosmos/tmp_files",
        required=True,
    )
    p.add_argument("-q", "--default-queue", help="aws batch queue", required=True)
    p.add_argument(
        "-o", "--out-s3-uri", help="s3 uri to store output of tasks", required=True,
    )
    p.add_argument("--core-req", help="number of cores to request for the job", default=1)
    p.add_argument(
        "--sleep",
        type=int,
        default=0,
        help="number of seconds to have the job sleep for.  Useful for debugging so "
        "that you can ssh into the instance running a task",
    )

    p.add_argument(
        "--max-attempts",
        default=2,
        help="Number of times to retry a task.  A task will only be retried if it is a spot instance because of the "
        "retry_only_if_status_reason_matches value we set in the code.",
    )
    return p.parse_args()


def main():
    args = parse_args()

    cosmos = Cosmos(
        "sqlite:///%s/sqlite.db" % os.path.dirname(os.path.abspath(__file__)),
        default_drm="awsbatch",
        default_drm_options=dict(
            container_image=args.container_image,
            s3_prefix_for_command_script_temp_files=args.s3_prefix_for_command_script_temp_files,
            # only retry on spot instance death
            retry_only_if_status_reason_matches="Host EC2 .+ terminated.",
        ),
        default_queue=args.default_queue,
    )
    cosmos.initdb()

    sp.check_call("mkdir -p analysis_output/ex1", shell=True)
    os.chdir("analysis_output/ex1")
    workflow = cosmos.start("awsbatch", restart=True, skip_confirm=True)

    t = workflow.add_task(
        func=get_instance_info,
        params=dict(out_s3_uri=args.out_s3_uri, sleep=args.sleep),
        uid="",
        time_req=None,
        max_attempts=args.max_attempts,
        core_req=args.core_req,
        mem_req=1024,
    )
    workflow.run()

    print(("task.params", t.params))
    print(("task.input_map", t.input_map))
    print(("task.output_map", t.output_map))
    print(("task.core_req", t.core_req))
    print(("task.time_req", t.time_req))
    print(("task.drm", t.drm))
    print(("task.uid", t.uid))
    print(("task.drm_options", t.drm_options))
    print(("task.queue", t.queue))

    sys.exit(0 if workflow.successful else 1)


if __name__ == "__main__":
    main()
