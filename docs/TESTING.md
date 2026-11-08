# Тестирование PhotoSorter (beta)

В репозитории **одна актуальная CI-система**: `.github/workflows/ci.yml`, запускается при push в `main` и `feature/ad-recognition`, а также PR в `main`. Проверки изолированы от VPS и пользовательских данных.

## Что запускается автоматически

| Job | Что проверяет |
|---|---|
| `backend` | Python 3.11, PostgreSQL 17, миграции, pytest, security, upload, ZIP, queue, Caddy и Compose config |
| `restore` | Реальные `pg_dump` → `pg_restore` в disposable PostgreSQL, SHA-256 и inode на синтетических файлах |
| `frontend` | Node 24 `npm ci`, строгий TypeScript/Vite build, Vitest, Playwright Chromium/WebKit desktop/mobile на моковом API |
| `docker-runtime` | Полная сборка CPU PyTorch и Docker, HTTPS self-signed, login/cookie, `/`, `/fo`, 404 на retired UI, три background heartbeat и синтетическая партия |

Этап 4: `test_processing_dashboard.py` проверяет фильтры `GET /runs?scope=active|history`, совместимость без scope, реальные DB-статусы и пагинацию. `frontend/tests/processingDashboard.test.ts` проверяет FIFO, running/stopping и метрики только при наличии измерений. Playwright проверяет новый dashboard на Chromium/WebKit desktop/mobile, Worker heartbeat, очередь, stop-confirm и отсутствие прежней формы запуска. **Реальные сетевые обрывы/перезапуск VPS тестами CI не заменяются**: [ручной чек-лист](STAGE4_ACCEPTANCE.md).

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


## Единый beta pipeline

Очередь ФО и подготовок образцов — только `work_queue.seq`; загрузка образцов всегда доступна через `/api/reference-imports` и сохраняет файлы в `reference_staging`. После полной подготовки публикуется неизменяемая версия библиотеки. Обе версии планировщика и условные флаги переключения удалены. Приёмка — тесты на пустой базе, докачку, FIFO, публикацию и браузеры Chromium/WebKit. Текущая архитектура: [REFERENCE_PIPELINE](REFERENCE_PIPELINE.md).

## Проверки этапа 1: разметка экранов

- `pytest PhotoSorter/backend/tests/test_screen_annotations.py` — геометрия, EXIF, PostgreSQL CRUD, FK, конструкция, версия.
- `npm run build && npm run test && npm run test:e2e` из `PhotoSorter/frontend` — TypeScript, Vitest и Chromium/WebKit; `screen-annotations.spec.ts` проверяет сохранение после перезагрузки.
- Параллельно прежние регрессионные проверки и Docker smoke в CI.
- На новом VPS дополнительно вручную проверить разметку нескольких реальных Образцов в iOS Safari и реальную MegaLoc/ZIP обработку. Успешный CI не означает проверку реальных ФО.


## Этап 2: XFeat / OpenCV на CPU

- `PhotoSorter/backend/tests/test_screen_search.py`: MAGSAC на плоской
  четырёхугольной поверхности с выбросами, отказ при 4 точках/одной стороне/
  координатах вне кадра; маска полосы без рекламы; сохранение оригинального crop.
- `app.screen_detection.cpu_smoke` внутри worker в одноразовом Docker CI:
  настоящие проверенные XFeat pretrained weights, детекция sparse-признаков,
  mutual descriptor match, измеренное время и RAM.
- Vue build, Vitest, Chromium и WebKit desktop/mobile остаются обязательны.
- Отдельная **обязательная полевая приёмка**: реальные LED-фото с разными
  рекламами, расстояниями, наклоном, ночью, бликами и несколькими экранами,
  c ручной разметкой верного экрана. Синтетические тесты и CPU smoke не
  подтверждают реальную точность.
