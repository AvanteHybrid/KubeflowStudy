# Kubeflow setup

## on-premis cluster setup with kubeadm

on-premise kubernetes cluster를 셋업하는 방법은 크게 세 가지 있는 것 같다.

1. (test) minikube 등의 테스트용 k8s 환경 구축.
2. (production) k8s bootstrapping tool인 kubeadm을 사용하여 환경 구축.
3. (production) kubelet, kube-apiserver 등 k8s 구성 요소를 모두 수동으로 설치.

실험용으로 kubeflow를 빠르게 셋업하기 위해서는 1번 방법이 제일 적절할텐데, production 환경의 k8s 셋업을 경험해볼 겸 kubeadm을 사용해보았다. kubeflow compatibility를 위해 1.21.0 버전을 설치했다. 또한, 사용중인 리눅스 장비 호스트에서 직접 셋업을 했는데, 사용환경과 충돌하는 부분이 좀 있어서 k8s를 위한 별도 VM을 셋업하고 그 위에서 세팅을 하는 것도 좋은 방법일 것 같다. 혹은 실제 production 환경에서 셋업한다면 해당 노드를 k8s dedicated 머신으로 두고 사용하는 것이 안전할 것 같다.
[공식 문서](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/)와 많은 개인 블로그에서 자세한 설치 내용이 설명되어있으니,
이 문서에서는 내가 셋업하면서 겪었던 trouble shooting 위주로 기록해보려고 한다.

1. swap 메모리 설정 해제
kube-apiserver와의 통신 및 pod 프로비저닝을 담당하는 kubelet이 정상 작동하기 위해서는 스왑 메모리 해제가 필요하다. 그렇지 않을 경우 kubeadm init 명령어 입력 시 아래와 같은 에러 메시지가 발생한다.

    > [ERROR Swap]: running with swap on is not supported. Please disable swap

2. cri plugin enablement
k8s는 다양한 컨테이너 런타임에 대응하기 위해 cri를 통해 인터페이싱한다. 내가 사용한 로컬 머신의 containerd config 파일 (`/etc/containerd/config.toml`) 에서는 `distabled_plugins = ["cri"]로 세팅이 되어있는데, 이로 인해 아래와 같은 에러가 발생하였다. "cri" 텍스트를 삭제하니 정상작동하였다.

    > failed to pull image "k8s.gcr.io/kube-apiserver:v1.24.0": output: time="2022-05-17T02:10:44+07:00" level=fatal msg="pulling image: rpc error: code = Unimplemented desc = unknown service runtime.v1alpha2.ImageService"

3. `--pod-network-cidr` 설정
마음이 급해서 kubeadm init 명령어에 별다른 아규먼트를 추가하지 않고 실행했었는데, 이 때문에 network addon이 제대로 설치되지 않았고, 따라서 istio 등 네트워크 관련 리소스가 제대로 provisioning 되지 않았다. calico 공식 다큐먼트의 [quick start](https://projectcalico.docs.tigera.io/getting-started/kubernetes/quickstart) 페이지의 가이드를 따라 `--pod-network-cidr` 설정 후 calico 설치를 하니 문제 없이 동작했다.

## kubeflow setup with manifests

클라우드 사업자의 지원 없이 on-premise 환경에서 kubeflow를 셋업할 경우, [manifests](https://github.com/kubeflow/manifests/tree/v1.5.0)를 이용하되, 로컬 환경의 실패에 실패에 대해서 kubeflow 측에서 책임이 없다고 명시한다..

우선 kubeflow의 컴포넌트들이 볼륨을 마운트 할 수 있게 default storage class 및 persistent volume을 셋업해두어야 한다. pv의 경우 여러 개 세팅해두어 다양한 pvc에 바인딩 될 수 있게 세팅해두어야한다.

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: standard
  annotations: { "storageclass.kubernetes.io/is-default-class": "true" }
provisioner: kubernetes.io/no-provisioner
volumeBindingMode: WaitForFirstConsumer
---
apiVersion: v1
kind: PersistentVolume
metadata:
  name: local-volume-1
  labels:
    type: local
spec:
  storageClassName: standard
  accessModes:
    - ReadWriteOnce
    - ReadOnlyMany
    - ReadWriteMany
  capacity:
    storage: 20Gi
  persistentVolumeReclaimPolicy: Recycle
  volumeMode: Filesystem
  hostPath:
    path: "/local/mnt/k8s/1"
```

몇 번의 삽질 끝에 아래와 같이 manifests 에 기술된 모든 컴포넌트들을 설치할 수 있었다.
![image](https://user-images.githubusercontent.com/19547969/190549504-6b70b7ff-7acb-4833-ae1f-98dd45708e6b.png)

readme에 적힌대로 port-forwarding 을 하니 centraldashboard ui가 보이는 것을 확인할 수 있다.
외부에 노출될 수 있도록 nodePort 서비스 설정을 시도해보았는데, istio 단에서 RBAC 인증 에러를 발생시키는 것 같다. (`RBAC: access denied`)
![image](https://user-images.githubusercontent.com/19547969/190549314-9b6f90c2-3de5-423e-af8f-2c6d6c907cd6.png)

실제 노트북 생성을 시도해보았는데 아래와 같이 실패하는 것을 확인했다. 다른 컴포넌트들도 현재 Running status로 확인되더라도 정상작동하지 않는 경우가 있을 것으로 보인다.
![image](https://user-images.githubusercontent.com/19547969/190553034-9766a31c-ab43-4e5d-98f9-23cd8fa37e43.png)


## 다음 주 목표
- centraldashboard를 hostname 및 port를 통해 접근 가능하도록 세팅하기
- notebook 404 에러 트러블슈팅
- notebook상에서 GPU 사용 가능한 지 확인하고 MNIST 모델 학습하기

