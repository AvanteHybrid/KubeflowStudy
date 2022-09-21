# Kubeflow Setup with Minikube
Minikube를 이용해 간단하게 k8s 환경을 구축하고 Kubeflow를 설치해보았다.
[이 블로그 포스트](https://1week.tistory.com/113)를 보고 거의 따라 했는데, 버전에 따라서 문제가 생길 수 있으니 버전을 잘 맞추는 것이 중요하다.

**사용한 버전들**:
* Minikube v1.21.6
* Kubernetes v1.21.0
* Kubeflow v1.4.1
* Kustomize v3.2.0

## Install minikube & set up k8s cluster
Minikube 설치를 위해 [공식 문서](https://minikube.sigs.k8s.io/docs/start/)를 참고했다.
설치하려는 머신에 따라서 알맞게 옵션을 선택하고 설치하면 끝이다.

Minikube를 이용해서 k8s 클러스터를 생성해야 한다.
Kubeflow가 설치 및 실행 될 수 있을 정도의 리소스를 할당하는 것과, 알맞는 k8s 버전을 명시하는 것이 중요하다.
* e.g.) minikube start --kubernetes-version=v1.21.0 --memory=8g --cpus=4 --profile kf
Minikube로 k8s를 구성하면 Kubeflow 설치에 필요한 default storage class 등이 자동으로 구성된다고 한다.

## Install Kubeflow
### Use Kustomize to install with single command
Kubeflow 설치를 위해서는 Kustomize라는 툴을 사용한다고 한다.
Kustomize는 Kubernetes 오브젝트를 kustomization 파일을 이용하여 사용자화할 수 있는 툴이라고 한다.
Kustomize 설치는 [이 링크](https://github.com/kubernetes-sigs/kustomize/releases/tag/v3.2.0)에서 파일을 다운 받아 쓰면 된다.

### Single-line Installation
Kubeflow 설치는 여러 방법이 있겠지만 Kubeflow github에 나오는 single-command 방법을 사용했다.
```bash
$ git clone https://github.com/kubeflow/manifests.git
$ cd manifests
$ git checkout v1.4.1  # 원하는 버전
$ while ! kustomize build example | kubectl apply -f -; do echo "Retrying to apply resources"; sleep 10; done
```
위 커맨드대로 하고 문제가 없다면 Kubeflow 설치 및 실행이 완료된다.

### NOTE
추후에 dashboard를 통해 Jupyter Notebook을 생성하려고 하니 아래와 같은 에러가 발생했다:
```bash
Could not find CSRF cookie XSRF-TOKEN in the request. 
```
이 문제는 [블로그 포스트](https://otzslayer.github.io/kubeflow/2022/06/11/could-not-find-csrf-cookie-xsrf-token-in-the-request.html)를 참고하여 해결했다.
HTTP의 보안 문제 때문에 발생한 이슈인데, HTTPS로 접근하게 하려다 블로그 주인분처럼 삽질만 엄청 하다가 실패했다.
결국 HTTP 접근을 허용하는 방식을 선택하고 말았는데.. HTTPS 접근을 허용하기 위한 방법은 블로그에도 언급되어 있으니 참고해서 진행하면 좋을듯 하다.

## Using Kubeflow Dashboard
Kubeflow 설치/실행을 완료하면 Kubeflow의 다양한 컴포넌트들이 k8s 클러스터에서 실행되고 있을 것이다.
그 중 하나인 Dashboard에 접속하기 위해서 URL 정보를 `istio-ingressgateway` 서비스에서 찾아야 한다.
```bash
$ minikube service list -p kf
```

만약 Kubeflow가 remote 머신에 deploy 되어 있고, 로컬 머신에서 Dashboard에 접근하고 싶은 경우에는 port forwarding 기능을 사용해야 한다.
```bash
$ kubectl port-forward -n istio-system service/istio-ingressgateway 8081:80 --address=0.0.0.0
```

## Creating Jupyter Notebook via Dashboard
Dashboard에서 Jupyter notebook을 생성할 수 있다.
노트북마다 리소스와 도커 이미지 등을 명시해서 생성할 수 있는데, GPU 리소스를 선택하니 무한 대기상태가 되어버렸다. 
GPU를 사용하기 위해서는 따로 조치가 필요해보인다..

찾아보니 Minikube에서 GPU 리소스를 사용하려면 설정해줘야 하는 것들이 있었다. [공식 문서](https://minikube.sigs.k8s.io/docs/tutorials/nvidia_gpu/)
`--driver=kvm2` 옵션과 `--driver=none` 옵션이 있는데 후자가 더 간단해보여서 후자로 진행했다.
공식 문서가 너무 불친절해서 [이 블로그 포스트](https://anencore94.github.io/2020/08/19/minikube-gpu.html)를 참고해서 설치했다.

`--driver=none`으로 해서 `minikube start`를 하게 되면 `--profile` 옵션도 줄 수 없고 `--cpus`나 `--memory` 옵션도 무시 당한다.
그냥 localhost 전체 리소스를 사용하게 되나보다.

다 완료 한 뒤에 GPU 리소스가 할당 된 Jupyter notebook을 생성할 수 있었다.