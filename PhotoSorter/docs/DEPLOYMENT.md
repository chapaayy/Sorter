# Legacy deployment note

Текущие эксплуатационные ограничения и полная инструкция по безопасной подготовке тестового стенда перенесены в [../../docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md). Важно: новая `cleanup`-служба и миграции допустимы **только после backup+restore-test и отдельного разрешения на VPS**. Стабильный production остаётся на исходной `vps/docker-rebuild`.

 
С этапа 2 появились отдельный контейнер `thumbnail`, очередь задач WebP и worker CPU 7/cpuset 0–6 (эксперимент для 8-vCPU staging). Полные инструкции в [../../docs/OPERATIONS.md](../../docs/OPERATIONS.md) и [../../docs/PERFORMANCE.md](../../docs/PERFORMANCE.md). Код не развёрнут на рабочем VPS, никаких реальных каталогов не очищали.
