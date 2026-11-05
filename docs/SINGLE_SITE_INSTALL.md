# Чистая установка PhotoSorter — один сайт на основном домене

## Единственная актуальная версия UI

Ветка `release/single-ui-root` поверх `stage4/validation-backup-rollout`.
`https://DOMAIN/` отдаёт Vue 3 (без `/v3/`). Только backend API находится на `/api/`.
В проекте нет старого HTML/JS/CSS frontend. Отдельного второго Docker/frontend-сервиса нет.

## Новый чистый VPS

Нужны Linux x86-64, Docker Engine + Compose v2, Python 3, реальный домен с DNS на VPS,
доступные 80/443 и подходящие CPU affinity (по умолчанию 0–6). Скопируйте проект:

```bash
git clone --branch release/single-ui-root --single-branch https://github.com/chapaayy/Sorter.git
cd Sorter
cp .env.example .env
nano .env              # DOMAIN=ваш-реальный-домен
bash ./install.sh --deploy
docker compose --env-file .env --env-file .env.generated ps
```

Скрипт для новой установки создаст `.env.generated`, настроит каталоги, соберёт Vue
и CPU backend и поднимет Caddy, PostgreSQL, API, worker, thumbnail и cleanup.
Первый вход `admin`, случайный пароль в `.env.generated`. Храните его в секрете.
Проверить `https://DOMAIN/`, `/fo`, `/references`, `/api/health`.

## Уже работающий VPS: важное предупреждение

Просто новый `git clone` в другой каталог на том же VPS **НЕ** создаёт чистую БД.
Compose фиксирует имя проекта `outdoor-sorter`: повторно используются volumes
`outdoor-sorter_postgres_data`, `outdoor-sorter_caddy_data`,
`outdoor-sorter_caddy_config`. Существующий `.env.generated` содержит пароли
действующей БД, и их нельзя молча перегенерировать.

На прежнем сервере уже могут храниться важные SAM, ФО, результаты и модели.
Сначала обеспечить проверенную независимую резервную копию PostgreSQL, 
`PhotoSorter/data`, `Models`, `.env`, `.env.generated` и volumes Caddy.
Затем явно решить, что означает «с нуля»:

1. **Чистая сборка кода с сохранением данных:** перейти на release-коммит, проверить
   `./install.sh --check`, обновить образы после проверки backup/restore. Веса,
   SAM и БД сохраняются.
2. **Полный сброс состояния:** отдельное окно обслуживания и явное подтверждение
   полного удаления исходных ФО, SAM, истории, PostgreSQL и при необходимости моделей.
   Требует остановки контейнеров, подтверждённой внешней копии и контролируемого
   удаления указанных данных и volumes. Нельзя считать это обычным `git pull`
   и нельзя запускать `docker compose down -v` как часть обновления.

В этой ветке **нет автоматической команды очистки**: чистая установка не должна
случайно удалять чужие данные. Запросить отдельный план сброса для конкретного VPS.

## Тестирование

```bash
cd PhotoSorter/frontend
npm ci
npm run build
npm run test
npm run test:e2e
```

CI также проверяет реальные Docker-build/startup, auth, deep links, root/index
и отсутствие legacy маршрутов на временном стенде, но не заменяет проверку
реальных MegaLoc 189/1315-ФО и полноценный restore production.
