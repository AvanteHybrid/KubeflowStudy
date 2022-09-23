# Trouble shooting issues with Kubeflow 1.5.0

지난 주에 진행한 내용은 아래와 같다.

- single-node kubernetes cluster setup with kubeadm (version==1.4.21)
- kubeflow setup in kubernetes cluster with kustomization (kubeflow==1.5.0, kustomization==3.2.0)

대시보드 UI를 port-forwarding을 통해 확인할 수 있었지만 아래와 같은 과제가 남았으며, 이 사항들을 하나씩 해결해보려고 한다.

- centraldashboard를 hostname 및 port를 통해 접근 가능하도록 세팅하기
- notebook 404 에러 트러블슈팅
- notebook상에서 GPU 사용 가능한 지 확인하고 MNIST 모델 학습하기

## centraldashboard를 hostname 및 port를 통해 접근 가능하도록 세팅하기

별도의 nodePort와 ingress 리소스를 통해서 centraldashboard 및 다른 ui 서비스를 외부로 노출시키고자 노력했는데, 결론적으로는 별도의 세팅 필요 없이 서버 호스트 네임 및 포트를 통해 외부에서 centraldashboard에 접근이 가능했다.
kubeflow 네임스페이스의 서비스들이 `istio-ingressgateway`를 통해 관리되고 있는데, 해당 리소스의 스펙을 확인해보니 아래와 같은 내용이 있었다. 혹시 몰라 `http://$HOSTNAME:31272`로 접근해보니 정상 접근이 가능했다.
물론 http를 통해 접근할 경우 리소스 프로비저닝을 요하는 동작을 했을 때 인증 관련 에러가 발생한다.
정상 동작을 위해서는 [이슈](https://github.com/kubeflow/kubeflow/issues/5803)에 가이드된 것과 같이 모든 앱에 `APP_SECURE_COOKIES=False` 환경변수를 세팅하거나
호스트 머신에 ssl certificate을 생성하여 https로 접근 가능하게 세팅해야한다.

```yaml
ports:
  ...
  - name: http2
    nodePort: 31272
    port: 80
    protocol: TCP
    targetPort: 8080
  - name: https
    nodePort: 30484
    port: 443
    protocol: TCP
    targetPort: 8443
  ...
```

## notebook 404 에러 트러블슈팅

단순 실수였다. `notebook-controller`가 설치되지 않았었다.

## notebook상에서 GPU 사용 가능한 지 확인하고 MNIST 모델 학습하기

### k8s 노드에 GPU 정보 입력하기

공식 문서상 [Schedule GPUs 페이지](https://kubernetes.io/docs/tasks/manage-gpus/scheduling-gpus/)를 참조하여 우분투 머신에 연결되어있는
NVIDIA GeForce RTX 2080 Ti GPU 한 개를 쿠버네티스 가용 자원에 등록하고자 한다.

먼저 [문서](https://github.com/NVIDIA/k8s-device-plugin#configure-docker)에서 가이드되는 것 처럼 docker의 daemon config json 파일을 수정하여 nvidia를 디폴트 컨테이너 런타임으로 등록한다.
이후에 아래와 같이 GPU 디바이스 플러그인을 설치한다.

```bash
kubectl create -f https://raw.githubusercontent.com/NVIDIA/k8s-device-plugin/1.0.0-beta4/nvidia-device-plugin.yml
```

노드에 GPU 관련 label을 달아둔다.

```bash
kubectl label nodes $HOSTNAME accelerator=nvidia-rtx-2080-ti
```

아래와 같이 지정한 accelerator label과 gpu 리소스를 사용하는 pod을 생성해본다.

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: cuda-vector-add
spec:
  restartPolicy: OnFailure
  containers:
    - name: cuda-vector-add
      # https://github.com/kubernetes/kubernetes/blob/v1.7.11/test/images/nvidia-cuda/Dockerfile
      image: "registry.k8s.io/cuda-vector-add:v0.1"
      resources:
        limits:
          nvidia.com/gpu: 1
  nodeSelector:
    accelerator: nvidia-rtx-2080-ti
```

Status가 completed로 확인되며, 로그를 살펴봐도 문제 없이 성공한 것으로 보인다.

```bash
$ kubectl logs cuda-vector-add
[Vector addition of 50000 elements]
Copy input data from the host memory to the CUDA device
CUDA kernel launch with 196 blocks of 256 threads
Copy output data from the CUDA device to the host memory
Test PASSED
Done
```

### jupyter notebook 생성하기
![image](https://user-images.githubusercontent.com/19547969/191887428-4d334fd9-80eb-44c2-9b45-750157ffde27.png)
- 기본적으로 제공되는 `jupyter-pytorch-cuda-full:v1.5.0` 이미지를 사용했으며, 메모리를 10Gi 할당했다.
- 사용 가능한 이미지 리스트는 manifests 레포지토리의 아래 config 파일에서 설정 가능한 것으로 보인다.
   - manifests/apps/jupyter/jupyter-web-app/upstream/base/configs/spawner_ui_config.yaml
- private registry를 사용하는 경우 해당 registry에 대한 인증은 어떻게 할 수 있는 지 알아보면 좋을 것 같다.

![image](https://user-images.githubusercontent.com/19547969/191888183-b3a73e4e-c06d-4d92-869a-9fb0f9e063d1.png)
- 생성이 완료되면 설정된 namespace에 jupyter notebook을 실행하는 pod이 실행된다. 설정사항이 spec에 반영되어있는 것을 확인할 수 있다.

![image](https://user-images.githubusercontent.com/19547969/191887518-2a3edea7-3b75-4fa9-9227-3f7e6c63f1dd.png)
- 문제 없이 작동함을 확인했다.

다음 주까지는 pipeline을 살펴보고, 간단한 파이프라인을 구축해보려고 한다.
