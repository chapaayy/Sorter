# Тесты, baseline и пределы проверки

## Команды

```bash
python -m compileall -q PhotoSorter/backend
PYTHONPATH=PhotoSorter/backend python -m pytest -q PhotoSorter/backend/tests
docker compose --env-file .env --env-file .env.generated config --quiet
```

CI `.github/workflows/ci.yml` поднимает **временный Postgres 17** (`sorter_test`) и запускает те же Python tests на Ubuntu Python 3.11, не подключаясь к VPS. Unit без PostgreSQL можно запускать отдельно — DB cases будут пропущены.

| Проверка | Где |
|---|---|
| 0.50 grouping, функции ФО→группы→SAM | `test_grouping.py` |
| прогресс/ETA без вымышленных процентов | `test_progress_ring.py` |
| hardlink inode/hash, unlink одного имени, EXDEV, duplicate | `test_stage1_lifecycle.py` |
| старая SQL схема + additive migration, idempotency | `test_stage1_lifecycle.py`, disposable schema |
| owned deletion 0/2 runs, другая партия, references | `test_stage1_lifecycle.py` |
| active ZIP/upload lease, running/queued job, retry after exception | `test_stage1_lifecycle.py` |
| архив zipstream читабелен, прежний SAM layout | `test_stage1_lifecycle.py` |
| +2 календарных месяца, 7-day warning/extension | `test_stage1_lifecycle.py`; необходимы также clock tests |
| 189/1315 реальных ФО и профиль CPU | **не хранится в repo, не заявлять пройденным** |
| полная restore проверка, TLS, Docker on VPS | **только на staging с разрешением** |

Тесты обязаны писать исключительно в `tmp_path` и disposable DB; не подключать `DATABASE_URL` производственной системы. CI не заменяет восстановление архивов и длительное тестирование на Linux volume, которое запланировано в этапе 4.
