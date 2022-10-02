import kfp
from kfp import dsl
from kfp.components import OutputPath, create_component_from_func
from pathlib import Path


def produce_metrics(
    eval_result_json_path: str,
    mlpipeline_metrics_path: OutputPath("Metrics"),
):
    # hardcoded for certain application
    import json

    js = json.load(open(eval_result_json_path, "r"))
    keys = "accuracy_top-1", "accuracy_top-5", "precision", "recall", "f1_score"
    metrics = {
        "metrics": [
            {
                "name": key,
                "numberValue": js[key] / 100,
                "format": "PERCENTAGE",
            }
            for key in keys
        ]
    }
    with open(mlpipeline_metrics_path, "w") as f:
        json.dump(metrics, f)


produce_metrics_op = create_component_from_func(
    produce_metrics,
    base_image="python:3.7",
    packages_to_install=[],
    output_component_file="component.yaml",
)


@dsl.pipeline(
    name="MMCLASSIFICATION Pipeline",
    description="Pipeline to train mmclassification models.",
)
def mmclassification_container_pipeline(
    data_path: str = "/mnt/data",
):
    """Run kubeflow pipeline for mmclf.
    Args:
        data_path (str): path to bind shared volume.
        config_path (str): mmclf config relpath (ex: )
    """
    # shared paths
    mmclf_config_path = "configs/resnet/resnet18_8xb16_cifar10.py"  # hardcoded
    container_work_dir = f"{data_path}/workspace"
    latest_ckpt_path = f"{container_work_dir}/latest.pth"
    container_eval_out_path = f"{container_work_dir}/eval_result.json"

    # define volume to share data between components
    vop = dsl.VolumeOp(
        name="create_volume",
        resource_name="mmclf-data-volume",
        size="5Gi",
        modes=dsl.VOLUME_MODE_RWM,
    )
    # Create mmclassification training operation
    training_container = dsl.ContainerOp(
        name="train_resnet",
        image="mmclf:latest",
        command=[
            "python3",
            "tools/train.py",
            mmclf_config_path,
            "--work-dir",
            container_work_dir,
        ],
        pvolumes={
            data_path: vop.volume,
        },
    )
    # Create mmclassification test operation
    testing_container = dsl.ContainerOp(
        name="test_resnet",
        image="mmclf:latest",
        command=[
            "python3",
            "tools/test.py",
            mmclf_config_path,
            latest_ckpt_path,
            "--out",
            container_eval_out_path,
            "--metrics",
            "accuracy",
            "precision",
            "recall",
            "f1_score",
        ],
        pvolumes={
            data_path: training_container.pvolume,
        },
    )
    # produce metrics
    metrics_container = produce_metrics_op(container_eval_out_path).add_pvolumes(
        {data_path: testing_container.pvolume}
    )


pipeline_conf = dsl.PipelineConf()
pipeline_conf.set_image_pull_policy("IfNotPresent")

kfp.compiler.Compiler().compile(
    pipeline_func=mmclassification_container_pipeline,
    package_path="mmclassification_pipeline.yaml",
    pipeline_conf=pipeline_conf,
)
