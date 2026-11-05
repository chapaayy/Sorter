# Stage 4 — аудит безопасности и приоритеты

## Сделано в ветке

- `server/security/login_throttle.py`: bounded 5 неправильных логинов / 10 минут для username и IP ключа, hashed ключи, `429`, всё поверх scrypt/constant-time проверки. Ограничение **в памяти одного API process** (для нескольких реплик нужен общий Redis/PostgreSQL limiter); restart сбрасывает историю, а атаки могут временно блокировать один account. Это best-effort, не WAF.
- `api/routes/downloads.py`: проверяет архивные относительные имена; Zip Slip через `..`, `/`, `\\`, NUL запрещён. Filesystem read lease до завершения ZIP сохраняется.
- `server/uploads.py`: превышение 30 млн пикселей отклоняется до публикации оригинала; тип изображения по Pillow, лимит файла 60 MiB, сохранён checksum/PATCH.
- `server/services/references.py`: запрещает переименовывать/удалять SAM, когда существуют опубликованные результаты, содержащие эту SAM. Старые manifests и reference paths не переписываются. Запрет может быть консервативным — нужен отдельный migration plan, если клиенту критично переименовывать использованные SAM.
- `server/storage/*`: ранее созданная защита от path traversal/symlink, владелец UUID, lease и экранирование. Stage4 тесты проверяют owned paths и ZIP имена.
- `install.sh`: не регенерирует пароль если существует PostgreSQL volume без `.env.generated`; не выводит секреты в лог, не делает recursive chown на апгрейде, требует явного backup approval token.
- `snapshot.py`: snapshot только после `--ack-writers-stopped`, рестор только в новый каталог со staging-маркером и БД `sorter_restore_*`, SHA-256 для всего включённого и проверка hardlinks. Никакие volumes не удаляются.
- `server/services/heartbeat.py`: реальные записи присутствия процессов, тайм-аут 35 сек, страница Настроек не объявляет worker работающим из-за пустой очереди.

## Не считать устранёнными без реального стенда

**P0:** подтверждённая внешняя зашифрованная копия VPS и успешный test restore; аудит сетевой изоляции API/Postgres, HTTPS/Caddy, прав настоящего Docker host; парольная политика владельца; ручное одобрение deployment.

**P1:** rate-limit API пока локален одному API-инстансу; `uvicorn --forwarded-allow-ips "*"` работает только если api не публично доступен и доверяет исключительно Caddy; убедиться в отсутствии publish ports Docker для API; fallback при смене CPU affinity; тесты 507 с реальным disk reserve.

**P1:** исторические SAM при попытке rename/delete возвращают 409; это осознанная защита существующих manifests, пока отсутствует безопасная миграция ссылок. В UI нужно показывать ошибку, не обходить блокировку.

**P2:** frontend Playwright mock API не заменяет реальный XSS/CSP/Safari accessibility audit. CSP отсутствует в Caddy: новый UI содержит inline initial-theme script, требуется отдельный CSP plan с hash/nonce; не вводить ломающий CSP без приёмки.

## Не изменялось

MegaLoc math/recognition, веса, source refs, пользовательские ФО и старый статический frontend. Все write-tests используют synthetic temporary files и disposable DB.
