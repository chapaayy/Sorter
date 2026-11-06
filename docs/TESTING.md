# Тестирование PhotoSorter (beta)

В репозитории **одна актуальная CI-система**: `.github/workflows/ci.yml`, запускается на push/PR в `main`. Проверки изолированы от VPS и пользовательских данных.

## Что запускается автоматически

| Job | Что проверяет |
|---|---|
| `backend` | Python 3.11, PostgreSQL 17, миграции, pytest, security, upload, ZIP, queue, Caddy и Compose config |
| `restore` | Реальные `pg_dump` → `pg_restore` в disposable PostgreSQL, SHA-256 и inode на синтетических файлах |
| `frontend` | Node 24 `npm ci`, строгий TypeScript/Vite build, Vitest, Playwright Chromium/WebKit desktop/mobile на моковом API |
| `docker-runtime` | Полная сборка CPU PyTorch и Docker, HTTPS self-signed, login/cookie, `/`, `/fo`, 404 на retired UI, три background heartbeat и синтетическая партия |

Этап 3: `test_batch_run_summaries.py` проверяет реальный PostgreSQL-статус, прогресс, порядок/пагинацию истории и ссылки на прежние результаты. `frontend/tests/batchProcessing.test.ts` проверяет все состояния, отсутствие ложного успеха по миниатюрам и отсутствие выдуманных процентов. Playwright проверяет очередь, отмену, остановку, мобильные карточки и историю результатов. UI не создаёт вторую очередь.

Этап 2: `test_auto_processing.py` проверяет default OFF, сохранение порога, ожидание полного манифеста, повторный/конкурентный enqueue, ручной запуск, отмену до enqueue и отсутствие авто-повтора после failed job. Браузерная проверка настроек выполняется на моковом API. Реальный сценарий отсутствия связи с клиентом требует приёмки на тестовом VPS.

Регрессионные тесты с именами `test_stage1_*`, `test_stage2_*`, `test_stage3_*`, `test_stage4_*` сохраняются **как тесты**, не как версии сайта. Их не нужно стирать при beta-cleanup.

## Локальные команды

```bash
python -m compileall -q PhotoSorter/backend PhotoSorter/tools
bash -n install.sh
PYTHONPATH=PhotoSorter/backend python -m pytest -q PhotoSorter/backend/tests

cd PhotoSorter/frontend
npm ci
npm run build
npm run test
npx playwright install chromium webkit
npm run test:e2e
```

Для backend с реальным SQL нужна **одноразовая** тестовая PostgreSQL 17 и переменная `DATABASE_URL` тестового инстанса. Никогда не указывать тестам production DB.

## Чего CI не доказывает

- MegaLoc с реальными эталонными 189 ФО (исторический ориентир 27 групп и 3 неопределённых) при тех же весах.
- 1315 полноразмерных ФО с реальной скоростью инференса/передачи и ZIP.
- Восстановление **реального** offsite backup PhotoSorter на отдельном VPS.
- Поведение Safari на физическом iPhone и качество photo preview при слабой сети.
- Длительную работу на пользовательской файловой системе/volume, реальный CPU/RAM/disk под нагрузкой.

Скрипты для ручной проверки:
- `PhotoSorter/tools/maintenance/compare_baseline.py` — сравнение предоставленных manifest/ZIP.
- `PhotoSorter/tools/maintenance/staging_probe.py` — только GET; p50/p95 API и resource/worker stats.
- `PhotoSorter/tools/maintenance/snapshot.py` — согласованный backup/verify/isolated restore-test.

Выполнение операций на пользовательском VPS возможно лишь с отдельно сохранённой копией и пониманием влияния на данные. См. [ACCEPTANCE](ACCEPTANCE.md), [BACKUP_RESTORE](BACKUP_RESTORE.md), [ROLLOUT](ROLLOUT.md).
