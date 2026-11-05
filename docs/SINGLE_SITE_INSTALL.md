# PhotoSorter — одна бета-версия в main

**Актуальный код** — `https://github.com/chapaayy/Sorter`, ветка `main`. Сайт: `https://DOMAIN/` (Vue 3), API: `/api/*`. Других интерфейсов и путей `/v3/` нет.

## Чистая установка на новый сервер

Требования: Docker Engine + Compose v2, Python3, Linux x86-64, доступные 80/443 и реальный домен.

```bash
git clone --single-branch --branch main https://github.com/chapaayy/Sorter.git
cd Sorter
cp .env.example .env
nano .env                # DOMAIN=ваш.домен
bash ./install.sh --deploy
docker compose --env-file .env --env-file .env.generated ps
```

Installer создаст только новые секреты в `.env.generated` для новой пустой PostgreSQL, соберёт Vue/CPU runtime и запустит caddy, postgres, api, worker, thumbnail, cleanup.

## Ранее установленный VPS: что считать «с нуля»

Простое скачивание `main` в ту же папку **не** удаляет старые фото, образцы и БД. В `compose.yaml` постоянно используется `name: outdoor-sorter` и volumes `outdoor-sorter_postgres_data`, `outdoor-sorter_caddy_data`, `outdoor-sorter_caddy_config`. На VPS пользовательские файлы расположены в bind mounts `PhotoSorter/data` и `Models`.

При бета-тестировании можно осознанно выбрать один из режимов:

**А. Чистая новая сборка и сохранение данных.** Зафиксировать старый SHA, создать проверенный backup, переключить код на `main`, запустить `./install.sh --check`, затем одобренный `--deploy`. Все старые фото и SAM останутся, но UI будет только один.

**Б. Полная переустановка с пустой базой.** После проверки offsite backup и остановки всех writers отдельно удалить только те пользовательские директории/volumes, которые согласованы для сброса, затем заново установить `main` с новыми секретами. Этот режим удалит историю, сессии, партии и, если выбрано, SAM и веса MegaLoc. Чтобы не скачивать модель заново, можно сохранить `Models` даже при чистой БД.

**Важное различие:** удаление `postgres_data` без замены `.env.generated` и очистки нужных bind mounts не означает полностью чистую установку. Нельзя использовать один и тот же старый `.env.generated` как секретный файл новой базы, не проверив целостность авторизации и паролей. При сбросе только состояния модели и шаблоны можно оставить.

Не удалять `Models/`, `PhotoSorter/data/`, `.env.generated` и Docker volumes автоматически из `git pull`, установки или CI.

## Проверка после установки

```bash
docker compose --env-file .env --env-file .env.generated ps
docker compose --env-file .env --env-file .env.generated logs --tail=100 api worker thumbnail cleanup
```

Проверить HTTPS, `/api/health`, `/`, `/fo`, `/references`, вход и статус worker. После чистого сброса отсутствие ранее созданных партий и SAM — ожидаемое поведение. MegaLoc распознавание проверять на реальных тестовых ФО отдельно.

Дополнительно: [DEPLOYMENT](DEPLOYMENT.md), [BACKUP_RESTORE](BACKUP_RESTORE.md), [ROLLBACK](ROLLBACK.md).
