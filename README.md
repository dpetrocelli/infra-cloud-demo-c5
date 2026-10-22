# demo-c5 · La clase en vivo

Un stack completo: frontend (`web`, nginx), API (`api`, la FastAPI de la clase 4) y base de datos Postgres: un contenedor en local, Cloud SQL (gestionada) en GCP.
La página tiene una encuesta, un botón de aplausos (los emojis vuelan en la pantalla de todos) y muestra qué contenedor o Pod atendió cada pedido.
Primero se levanta con Docker Compose y después, sin tocar el código, en Kubernetes.

```
local:  navegador ──► web (nginx :80) ──/api/──► api (FastAPI :8080) ──► db (contenedor Postgres) ──► volumen
GKE:    navegador ──► web (3 Pods)     ──/api/──► api (2 Pods + Cloud SQL Auth Proxy) ──► Cloud SQL (demo-c5-db)
```

| Pieza | Docker Compose | Kubernetes (GKE) |
|---|---|---|
| Cómo `web` encuentra a `api` | la red del compose y el nombre del servicio | Service `api`: el mismo `nginx.conf` |
| Frontend sin estado | servicio `web`, `8080:80` | Deployment de 3 réplicas + Service LoadBalancer |
| API sin estado (los datos están en la base) | servicio `api` | Deployment de 2 réplicas + Service |
| Base de datos | servicio `db` + volumen `datos` | Cloud SQL `demo-c5-db`, vía el Auth Proxy dentro de cada Pod de la API |
| Credenciales | `.env` (fuera de Git) | Secret `db` (fuera de Git) + Workload Identity (sin claves) |

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

## 1. Docker Compose (el stack completo)

Las credenciales no están en el repo: salen de un `.env` local (ignorado por git).

```bash
cp .env.example .env            # y poner una contraseña propia en POSTGRES_PASSWORD
docker compose up -d --build
docker compose ps
```

La base no publica ningún puerto (solo la API, dentro de la red del compose, llega a ella) y Swagger escucha solo en `127.0.0.1`.
Si ya habías levantado el compose con otra contraseña, el volumen conserva la vieja: `docker compose down -v`.

Abrir http://localhost:8080, votar y aplaudir. Swagger de la API (sola): http://localhost:8000/docs.

- **La base:** los votos están en Postgres. `docker compose exec db psql -U demo -c "select * from votos"`.
- **El volumen:** `docker compose down` y `docker compose up -d`: los votos siguen ahí (`down -v` los borra).
- **Orden de arranque:** la API espera a que la base responda (`depends_on` con healthcheck, y reintenta al arrancar).
- **Nadie lo levanta:** `docker compose kill api` y la API queda caída hasta que alguien la arranque (`docker compose up -d`).
- **La IP cambia:** si al recrear `api` la página muestra "La API no responde", nginx resolvió `api` al arrancar y la IP cambió. Se arregla con `docker compose restart web`. En Kubernetes no pasa: el Service tiene una IP fija.

## 2. Push a Artifact Registry

Repo `demo-c5` (us-central1), con lectura pública: el cluster baja las imágenes sin credenciales.

```bash
docker compose build        # deja demo-c5-api:v1 y demo-c5-web:v1
docker tag demo-c5-api:v1 $AR/api:v1
docker tag demo-c5-web:v1 $AR/web:v1
docker push $AR/api:v1
docker push $AR/web:v1
```

## 3. Kubernetes a mano (namespace `clase5`)

La base ya existe: Cloud SQL `demo-c5-db` (Postgres 16, `db-f1-micro`), creada una vez con `scripts/setup-cloudsql.sh`.
Ese script también crea el Secret `db` (usuario y contraseña aleatoria, no está en ningún archivo) y la service account `api-cloudsql`, que solo puede conectarse a Cloud SQL.

```bash
kubectl get secret db            # tiene que existir (lo crea setup-cloudsql.sh)
kubectl apply -f k8s/
kubectl get pods,svc -o wide     # los Pods de la API muestran 2/2: la API y el proxy
kubectl get svc web -w           # esperar EXTERNAL-IP (1-2 min)
```

En otra terminal: `kubectl get pods -w`. Los alumnos entran a `http://<EXTERNAL-IP>:8080/` (con el puerto: sin él, Chrome intenta https y esta app no lo sirve).

- **Cómo llega la API a la base:** cada Pod de la API lleva el Cloud SQL Auth Proxy al lado. La API se conecta a `127.0.0.1:5432` como si Postgres fuera local; el proxy abre una conexión cifrada a la instancia, autenticado como `api-cloudsql` por Workload Identity. Sin IPs abiertas y sin claves JSON. Logs: `kubectl logs deploy/api -c cloud-sql-proxy`.
- **Balanceo:** el Pod de `web` cambia de color con cada actualización, y en "Aplausos" se ve cuántos atendió cada una de las 3 réplicas. Después de un rollout, los Pods viejos quedan atenuados.
- **Se recupera solo:** `kubectl delete pod -l app=web`; vuelven Pods nuevos, con otros nombres.
- **Prueba de fuego:** `kubectl delete pod -l app=api` (las dos réplicas). Vuelven Pods nuevos y los votos siguen: la API no guarda nada, todo está en Cloud SQL.
- **La API escala:** `kubectl scale deployment/api --replicas=4`. Todas las réplicas comparten la misma base.
- **Ver los datos:** `kubectl exec deploy/api -c api -- python -c "import psycopg; print(psycopg.connect().execute('select * from votos').fetchall())"`, o en la consola: Cloud SQL → `demo-c5-db` → Cloud SQL Studio (usuario `demo`; la contraseña: `kubectl get secret db -o jsonpath='{.data.password}' | base64 -d`).
- **Rolling update:**
  ```bash
  docker build -t $AR/web:v2 --build-arg WEB_VERSION=v2 web && docker push $AR/web:v2
  kubectl set image deployment/web web=$AR/web:v2
  kubectl rollout status deployment/web
  ```
  En la página, la versión del frontend pasa a `v2` sin cortes (probado: 0 pedidos fallidos durante el rollout). `kubectl rollout undo deployment/web` vuelve atrás.

## 4. El pipeline (`.github/workflows/deploy.yml`)

Cada push a `main` construye `api` y `web` con el sha como tag, hace el smoke test (un Postgres + api + web en el runner, como el compose, y comprueba que un voto llega a la base), los sube a Artifact Registry y los despliega en GKE con `kubectl apply`. Al final verifica que la página responda con la versión nueva: la tarjeta del front muestra el sha corto.

- **Sin contraseñas en el repo:** el Secret `db` lo crea una vez `scripts/setup-cloudsql.sh` y el `kubectl apply` del pipeline no lo toca; el smoke test usa una contraseña aleatoria por corrida.
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
kubectl exec deploy/api -c api -- python -c "import psycopg; psycopg.connect(autocommit=True).execute('TRUNCATE votos, aplausos, items')"
```

## Limpieza

```bash
kubectl delete namespace clase5                                  # Pods, Services, el Secret y el LoadBalancer
docker compose down -v
gcloud sql instances delete demo-c5-db                           # la base: deja de cobrar (borra los datos)
gcloud container clusters delete demo-c5 --zone us-central1-a    # el cluster: deja de cobrar
```
