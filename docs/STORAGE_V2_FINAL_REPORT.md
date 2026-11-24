# Финальная приёмка Storage V2 — отчёт на 25.11.2026

**Этап 10 открыт.** Ниже фактически полученные результаты и отдельные обязательные проверки; не разрешение на production rollout.

## Доказательства
- Закрывающий этап 9: 5ce1808, [CI 45494437011](https://github.com/chapaayy/Sorter/actions/runs/45494437011), 7/7.
- Реализация этапа 9: 6b14fb0, CI 45492993969, 378 backend tests + 28 subtests, три браузерных набора, restore и Docker runtime. Реальные offline MegaLoc, повторный deploy, проверка TLS/PG/файлов, сохранение модели/эмбеддингов, проверка дискового резерва обновлятора. Эти результаты относятся к предыдущей проверенной ревизии, не заменяют финальную проверку.
- Stage 10: 24dc058 — интерактивная настройка, b293bc9 — настоящий Ubuntu VM/systemd/reboot сценарий, 11f0cbd — реальная нагрузка, 8ee4607 — исправление тестов, cleanup и TLS источника корпуса.
- Первый [release run 45497828371](https://github.com/chapaayy/Sorter/actions/runs/45497828371): load остановлен до обработки из-за TLS сертификата COCO. Новый источник: HTTPS HF mirror, закреплённая ревизия fbbee70f52f540987cca6936c9f1d7b1ff969ad1, SHA-256 4f7e2ccb2866ec5041993c9cf2a952bbed69647b115d0f74da7ce8f4bef82f05. Никаких фиктивных метрик.

## Обязательные критерии
| Критерий | Статус |
|---|---|
| Единый контракт, отсутствие старых mounts | Реализовано и проверялось этапами 2–9; финальная сверка и регрессия отдельно |
| Чистая Ubuntu, автоматическая установка Docker и systemd, перезагрузка, обновление API | Сценарий создан, пока нет подтверждения прохождения |
| Основной функционал, права, квоты, восстановление | Предыдущая интеграционная и браузерная приёмка успешна; итоговый прогон обязателен |
| 1100 различных реальных фото, 3 тестовых видео, повторная сортировка, 3 цикла | Сценарий создан; не подтверждён |
| Фактические CPU/RAM, disk peak, скорость сверки и Chromium, ZIP TTL 1h | Нет измеренного отчёта, критерий открыт |
| Долговременный рост, очистка, сохранение модели после обновления | Предыдущие точечные проверки есть; комплексный цикл не подтверждён |
| Финальный CI | Требуется успех на финальном SHA |
| PR без merge | Отдельно фиксируется в прогрессе |

COCO — реальные публичные фотографии общего назначения, не размеченный набор конструкций SAM. Видео в нагрузочном сценарии сгенерированы для проверки кодеков. Даже успешный load не доказывает точность сортировки рекламных конструкций. Реальная Ubuntu VM проверяет localhost TLS, а не публичный ACME конкретного VPS. Локальная среда Debian без Docker/KVM; никакая ручная имитация systemd не принимается за успех. Метрики будут доступны только при фактическом выполнении job (JSON artifact). 

## Subsequent checkpoint
- [PR #22](https://github.com/chapaayy/Sorter/pull/22) opened as draft; main untouched, no merge.
- [Release 45498523215](https://github.com/chapaayy/Sorter/actions/runs/45498523215) downloaded and verified the pinned COCO archive but failed before processing due to ZipInfo sorting; corrected. A load report has not yet been produced.
- Backend CI 45498523284 revealed an old test fixture expecting unmanaged runs to be deleted. The updated fixture tests canonical managed cleanup and verifies unmanaged files survive. New API quota rejection probe added to the release load.
