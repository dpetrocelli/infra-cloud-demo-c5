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

## 1. Docker local

```bash
cd demo-c5
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
AR=us-central1-docker.pkg.dev/project-4c4f803f-f2a7-4566-9fe/demo-c5
docker tag demo-c5-api:v1 $AR/api:v1
docker tag demo-c5-web:v1 $AR/web:v1
docker push $AR/api:v1
docker push $AR/web:v1
```

## 3. Kubernetes (k3s `free-k3s` en GCP, namespace `ensayo-c5`)

```bash
kubectl apply -f k8s/
kubectl get pods,pvc,svc -o wide
```

En otra terminal: `kubectl get pods -w`.

Los alumnos entran a **http://35.209.42.61:30080**, o a cualquier otra VM de GCP del cluster en el puerto 30080.
El Service es `LoadBalancer`, pero en este k3s `servicelb` está apagado, así que `EXTERNAL-IP` queda `<pending>`: se entra por el `nodePort` fijo 30080. La regla de firewall `demo-c5-allow-web` abre solo ese puerto y solo en las VMs del cluster.

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

### Lo que este cluster tiene de particular (ya resuelto en `k8s/`)

- **No hay StorageClass default:** sin `storageClassName: local-path` el PVC queda `Pending` (`no storage class is set`).
- **Hay nodos en casa** (`knode06`, `knode11`, `dp-note`): una afinidad suave lleva los Pods a las VMs de GCP (`us-central1-a`). El disco de `local-path` queda en el nodo donde arrancó `api-0` por primera vez.
- **`imagePullPolicy: Always`:** si re-subís el mismo tag, el Pod nuevo lo baja de nuevo.
- En k3d anda igual: la afinidad es "preferida" y `local-path` existe.

## Antes de la clase: contadores en cero

```bash
kubectl delete statefulset api && kubectl delete pvc data-api-0 && kubectl apply -f k8s/
```

## Limpieza

```bash
kubectl delete -f k8s/ && kubectl delete pvc data-api-0      # el PVC no se borra con el StatefulSet
docker rm -f web api && docker network rm demo-c5 && docker volume rm demo-c5-datos
gcloud compute firewall-rules delete demo-c5-allow-web       # cierra el 30080
```
