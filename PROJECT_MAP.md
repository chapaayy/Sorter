# Project map

`Sorter/` состоит из `Models/` (веса + служебные данные нейросетей) и `PhotoSorter/` (приложение, данные, Docker-конфигурация). На уровне корня находятся оркестрация (`compose.yaml`), установка (`install.sh`) и документация.

- **Caddy:** `PhotoSorter/docker/caddy/Caddyfile`, публичный HTTPS reverse proxy.
- **Docker image:** `PhotoSorter/docker/app/Dockerfile`, общий образ API/Worker, CPU PyTorch, Python 3.11.
- **Web/API:** `PhotoSorter/backend/server/main.py`, приватные эндпоинты, результаты, ZIP, статика.
- **Authentication:** `server/auth.py`, admin, scrypt и cookie-сессии.
- **DB:** `server/database.py`, PostgreSQL схема и соединения.
- **Uploads:** `server/uploads.py`, возобновляемые блоки ФО/Образцов и SAM-пути.
- **Queue:** `server/jobs.py`, PostgreSQL job enqueue/progress.
- **CPU Worker:** `server/worker.py`, строго один потребитель очереди.
- **Reference cache:** `server/reference_cache.py`, только эмбеддинги Образцов.
- **MegaLoc:** `app/recognition/engines/megaloc/`, неизменённый экстрактор и загрузчик Stage 2.7.
- **Sorting math:** `app/recognition/pipeline.py`, `grouping/`, `matching/`, без новых алгоритмов.
- **Export:** `app/results/`, manifest и папки SAM.
- **Frontend:** `PhotoSorter/frontend/static/{index.html,app.js,style.css}`, 3 вкладки.
- **Data:** `PhotoSorter/data/`, bind mount, вне Git.
