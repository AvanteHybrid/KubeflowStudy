"""
Using katib in kubeflow pipeline.
(1) Tries random hparam search for two hparams ("learning_rate", "loss_weight") for mmclassification resnet18
(2) Use optimal hparam and fully train the model
(3) Save model and test accuracy

Reference: https://github.com/kubeflow/katib/blob/master/examples/v1beta1/kubeflow-pipelines/kubeflow-e2e-mnist.ipynb
"""

from pathlib import Path

import kfp
from kfp import dsl
from kfp.components import (
    OutputPath,
    create_component_from_func,
    load_component_from_url,
)
from kubeflow.katib import (
    ApiClient,
    V1beta1ExperimentSpec,
    V1beta1AlgorithmSpec,
    V1beta1ObjectiveSpec,
    V1beta1ParameterSpec,
    V1beta1FeasibleSpace,
    V1beta1TrialTemplate,
    V1beta1TrialParameterSpec,
    V1beta1MetricsCollectorSpec,
    V1beta1CollectorSpec,
    V1beta1SourceSpec,
    V1beta1FilterSpec,
)

# You should define the Experiment name, namespace and number of training steps in the arguments.
def create_katib_experiment_task(
    experiment_name, experiment_namespace, mmclf_config_path, container_work_dir
):
    # Trial count specification.
    max_trial_count = 5
    max_failed_trial_count = 3
    parallel_trial_count = 2

    # Objective specification.
    objective = V1beta1ObjectiveSpec(
        type="maximize", objective_metric_name="accuracytop5", goal=0.99
    )

    # Algorithm specification.
    algorithm = V1beta1AlgorithmSpec(
        algorithm_name="random",
    )

    # Experiment search space.
    # In this example we tune learning rate and batch size.
    parameters = [
        V1beta1ParameterSpec(
            name="learning_rate",
            parameter_type="double",
            feasible_space=V1beta1FeasibleSpace(
                min="0.01",
                max="0.05",
                step="0.01",
            ),
        ),
        V1beta1ParameterSpec(
            name="loss_weight",
            parameter_type="double",
            feasible_space=V1beta1FeasibleSpace(
                min="0.5",
                max="1.5",
                step="0.5",
            ),
        ),
    ]

    # Experiment Trial template.
    # TODO (andreyvelich): Use community image for the mnist example.
    trial_spec = {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "spec": {
            "template": {
                "metadata": {
                    "annotations": {
                        "sidecar.istio.io/inject": "false",
                    }
                },
                "spec": {
                    "containers": [
                        {
                            "name": "training-container",
                            "image": "mmclf:latest",
                            "imagePullPolicy": "IfNotPresent",
                            "command": [
                                "python3",
                                "tools/train.py",
                                mmclf_config_path,
                                "--work-dir",
                                container_work_dir,
                                "--cfg-options",
                                "optimizer.lr=${trialParameters.learningRate}",
                                "--cfg-options",
                                "model.head.loss.loss_weight=${trialParameters.lossWeight}",
                            ],
                        },
                    ],
                    "restartPolicy": "Never",
                },
            },
        },
    }

    # Configure parameters for the Trial template.
    trial_template = V1beta1TrialTemplate(
        primary_container_name="training-container",
        trial_parameters=[
            V1beta1TrialParameterSpec(
                name="learningRate",
                description="Learning rate for the training model",
                reference="learning_rate",
            ),
            V1beta1TrialParameterSpec(
                name="lossWeight", description="Loss weight", reference="loss_weight"
            ),
        ],
        trial_spec=trial_spec,
    )
    # Create a metric collector spec

    # metric_collector_spec = V1beta1MetricsCollectorSpec(
    #     collector=V1beta1CollectorSpec(kind="StdOut"),
    #     # source=V1beta1SourceSpec(
    #     #     filter=V1beta1FilterSpec(
    #     #         metrics_format=[r"([\\w|-]+)\\s*:\\s*((-?\\d+)(\\.\\d+)?)"],
    #     #     ),
    #     # ),
    # )

    # Create an Experiment from the above parameters.
    experiment_spec = V1beta1ExperimentSpec(
        max_trial_count=max_trial_count,
        max_failed_trial_count=max_failed_trial_count,
        parallel_trial_count=parallel_trial_count,
        objective=objective,
        algorithm=algorithm,
        parameters=parameters,
        trial_template=trial_template,
        # metrics_collector_spec=metric_collector_spec,
    )

    # Create the KFP task for the Katib Experiment.
    # Experiment Spec should be serialized to a valid Kubernetes object.
    katib_experiment_launcher_op = load_component_from_url(
        "https://raw.githubusercontent.com/kubeflow/pipelines/master/components/kubeflow/katib-launcher/component.yaml"
    )
    op = katib_experiment_launcher_op(
        experiment_name=experiment_name,
        experiment_namespace=experiment_namespace,
        experiment_spec=ApiClient().sanitize_for_serialization(experiment_spec),
        experiment_timeout_minutes=60,
        delete_finished_experiment=False,
    )

    return op


# This function converts Katib Experiment HP results to args.
def convert_katib_results(katib_results) -> str:
    import json
    import pprint

    katib_results_json = json.loads(katib_results)
    print("Katib results:")
    pprint.pprint(katib_results_json)
    best_hps = []
    for pa in katib_results_json["currentOptimalTrial"]["parameterAssignments"]:
        if pa["name"] == "learning_rate":
            best_hps.append("--cfg-options")
            best_hps.append("optimizer.lr=" + pa["value"])
        elif pa["name"] == "loss_weight":
            best_hps.append("--cfg-options")
            best_hps.append("model.head.loss.loss_weight=" + pa["value"])
    print("Best Hyperparameters: {}".format(best_hps))
    return " ".join(best_hps)


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


def save_model(
    latest_ckpt_path: str,
    model_path: OutputPath("Model"),
):
    import shutil

    shutil.copy(latest_ckpt_path, model_path)


convert_katib_results_op = create_component_from_func(convert_katib_results)

produce_metrics_op = create_component_from_func(
    produce_metrics,
    base_image="python:3.7",
    packages_to_install=[],
    output_component_file="produce_metrics.yaml",
)

save_model_op = create_component_from_func(
    save_model,
    base_image="python:3.7",
    packages_to_install=[],
    output_component_file="save_model.yaml",
)


@dsl.pipeline(
    name="MMCLASSIFICATION Pipeline",
    description="Pipeline to train mmclassification models.",
)
def mmclassification_container_pipeline(
    katib_experiment_name: str,
    katib_experiment_namespace: str = "kubeflow-user-example-com",
    data_path: str = "/mnt/data",
    mmclf_config_path="configs/resnet/resnet18_8xb16_cifar10.py",
):
    """Run kubeflow pipeline for mmclf.
    Args:
        data_path (str): path to bind shared volume.
        config_path (str): mmclf config relpath (ex: )
    """
    # shared paths
    container_work_dir = f"{data_path}/workspace"
    latest_ckpt_path = f"{container_work_dir}/latest.pth"
    container_eval_out_path = f"{container_work_dir}/eval_result.json"

    katib_op = create_katib_experiment_task(
        experiment_name=str(katib_experiment_name),
        experiment_namespace=str(katib_experiment_namespace),
        mmclf_config_path=str(mmclf_config_path),
        container_work_dir=str(container_work_dir),
    )

    best_hp_op = convert_katib_results_op(katib_op.output)
    best_hps = best_hp_op.output

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
        command=["sh", "-c"],
        arguments=[
            f"python3 tools/train.py {mmclf_config_path} --work-dir {container_work_dir} {best_hps}",
        ],
        pvolumes={
            data_path: vop.volume,
        },
    )
    # save model
    save_container = save_model_op(latest_ckpt_path).add_pvolumes(
        {data_path: training_container.pvolume}
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
