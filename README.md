# demo-c5 · La clase en vivo

Un frontend (`web`, nginx) y una API (`api`, la FastAPI de la clase 4) con un disco.
La página tiene una encuesta, un botón de aplausos (los emojis vuelan en la pantalla de todos) y muestra qué contenedor o Pod atendió cada pedido.
Primero se levanta con Docker y después, sin tocar el código, en Kubernetes.

```
navegador ──► web (nginx :80) ──/api/──► api (FastAPI :8080) ──► /data (votos.json, aplausos.json)
```

| Pieza | Docker | Kubernetes |
|---|---|---|
| Cómo `web` encuentra a `api` | red `demo-c5` y `--name api` | Service `api`: el mismo `nginx.conf` |
| Frontend sin estado | `docker run -p 8080:80` | Deployment de 3 réplicas + Service |
| API con estado | `-v demo-c5-datos:/data` | StatefulSet con PVC |

## 0. Variables y acceso al cluster (GKE `demo-c5`)

En Git Bash (Windows) o cualquier bash, parado en esta carpeta:

```bash
export CLOUDSDK_CORE_PROJECT=project-4c4f803f-f2a7-4566-9fe AR=us-central1-docker.pkg.dev/project-4c4f803f-f2a7-4566-9fe/demo-c5
gcloud container clusters get-credentials demo-c5 --zone us-central1-a
kubectl get nodes
kubectl create namespace clase5
kubectl config set-context --current --namespace=clase5
```

El cluster (una vez; tarda 5-10 min y cuesta mientras existe):

```bash
gcloud container clusters create demo-c5 --zone us-central1-a --num-nodes 2 --machine-type e2-medium \
  --disk-type pd-standard --disk-size 30 --release-channel regular --workload-pool=project-4c4f803f-f2a7-4566-9fe.svc.id.goog
```

## 1. Docker local

```bash
docker build -t demo-c5-api:v1 api
docker build -t demo-c5-web:v1 web
docker network create demo-c5
docker run -d --name api --network demo-c5 -v demo-c5-datos:/data demo-c5-api:v1
docker run -d --name web --network demo-c5 -p 8080:80 demo-c5-web:v1
```

Abrir http://localhost:8080, votar y aplaudir.

- **El volumen:** `docker rm -f api` y repetir el `run` de la API: los votos siguen ahí.
- **La IP cambia:** si al recrear `api` la página muestra "La API no responde", es porque nginx resolvió `api` al arrancar y la IP cambió. Se arregla con `docker restart web`. En Kubernetes no pasa: el Service tiene una IP fija.
- **Nadie lo levanta:** `docker kill api` y la API queda caída hasta que alguien la arranque a mano.

## 2. Push a Artifact Registry

Repo `demo-c5` (us-central1), con lectura pública: el cluster baja las imágenes sin credenciales.

```bash
docker tag demo-c5-api:v1 $AR/api:v1
docker tag demo-c5-web:v1 $AR/web:v1
docker push $AR/api:v1
docker push $AR/web:v1
```

## 3. Kubernetes a mano (namespace `clase5`)

```bash
kubectl apply -f k8s/
kubectl get pods,pvc,svc -o wide
kubectl get svc web -w          # esperar EXTERNAL-IP (1-2 min)
```

En otra terminal: `kubectl get pods -w`. Los alumnos entran a `http://<EXTERNAL-IP>:8080/` (con el puerto: sin él, Chrome intenta https y esta app no lo sirve).

- **Balanceo:** el Pod de `web` cambia de color con cada actualización, y en "Aplausos" se ve cuántos atendió cada una de las 3 réplicas. Después de un rollout, los Pods viejos quedan atenuados.
- **Se recupera solo:** `kubectl delete pod -l app=web`; vuelven Pods nuevos, con otros nombres.
- **Prueba de fuego:** `kubectl delete pod api-0`. La página muestra la API caída unos segundos y vuelve `api-0`, con el mismo nombre y los mismos votos.
- **Rolling update:**
  ```bash
  docker build -t $AR/web:v2 --build-arg WEB_VERSION=v2 web && docker push $AR/web:v2
  kubectl set image deployment/web web=$AR/web:v2
  kubectl rollout status deployment/web
  ```
  En la página, la versión del frontend pasa a `v2` sin cortes (probado: 0 pedidos fallidos durante el rollout). `kubectl rollout undo deployment/web` vuelve atrás.

## 4. El pipeline (`.github/workflows/deploy.yml`)

Cada push a `main` construye `api` y `web` con el sha como tag, hace el smoke test (los mismos dos `docker run`), los sube a Artifact Registry y los despliega en GKE con `kubectl apply`. Al final verifica que la página responda con la versión nueva: la tarjeta del front muestra el sha corto.

- **Sin claves:** GitHub se autentica con OIDC como `gke-deployer`, que solo puede subir al repo `demo-c5` y desplegar en el cluster. El provider `github-provider-c5` solo acepta este repo.
- **Kubernetes:** `get-gke-credentials` le arma el kubeconfig al runner con esas mismas credenciales. No hay kubeconfig guardado en ningún lado.
- **Pull request:** build y smoke test, nada se publica.
- Setup (una vez, como Owner): `scripts/setup-pipeline.sh`. Crea la service account, sus roles, el provider OIDC y las variables del repo.

```bash
gh workflow run deploy                      # o un push a main
gh run watch
```

## Antes de la clase: contadores en cero

```bash
kubectl delete statefulset api && kubectl delete pvc data-api-0 && kubectl apply -f k8s/
```

## Limpieza

```bash
kubectl delete namespace clase5                                  # Pods, Services, el LoadBalancer y el disco
docker rm -f web api && docker network rm demo-c5 && docker volume rm demo-c5-datos
gcloud container clusters delete demo-c5 --zone us-central1-a    # el cluster: deja de cobrar
```
