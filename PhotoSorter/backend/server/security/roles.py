"""Central allowlist for implemented, independently enforced permissions."""
from fastapi import HTTPException
from .scopes import allowed_for,covers,may_delegate

CATALOG={
    "results.view":{"label":"Просмотр готовых результатов","group":"Результаты"},
    "results.media":{"label":"Просмотр фото и видео результатов","group":"Результаты","requires":"results.view"},
    "results.zip":{"label":"Скачивание ZIP результатов","group":"Результаты","requires":"results.view"},
}
CATALOG.update({"photos.view":{"label":"Просмотр фотоотчётов","group":"Фотографии","scoped":True},"photos.create":{"label":"Создание фотоотчётов","group":"Фотографии","scoped":False},"photos.upload":{"label":"Загрузка файлов","group":"Фотографии","scoped":True,"requires":"photos.view"},"photos.rename":{"label":"Переименование","group":"Фотографии","scoped":True,"requires":"photos.view"},"photos.media":{"label":"Просмотр оригиналов и миниатюр","group":"Фотографии","scoped":True,"requires":"photos.view"},"photos.download":{"label":"Скачивание оригиналов","group":"Фотографии","scoped":True,"requires":"photos.view"},"photos.delete_file":{"label":"Удаление фотографий","group":"Фотографии","scoped":True,"requires":"photos.view"},"photos.delete":{"label":"Удаление фотоотчётов","group":"Фотографии","scoped":True,"requires":"photos.view"},"photos.process":{"label":"Запуск и повтор обработки","group":"Фотографии","scoped":True,"requires":"photos.view"},"photos.auto":{"label":"Управление автозапуском","group":"Фотографии","scoped":True,"requires":"photos.view"},"photos.retention":{"label":"Управление хранением фотоотчёта","group":"Фотографии","scoped":True,"requires":"photos.view"},"photos.prepare":{"label":"Повтор подготовки медиа","group":"Фотографии","scoped":True,"requires":"photos.view"},"references.view":{"label":"Просмотр образцов","group":"Образцы","scoped":False},"references.export":{"label":"Экспорт ZIP","group":"Образцы","scoped":False,"requires":"references.view"},"references.import":{"label":"Импорт и загрузка образцов","group":"Образцы","scoped":False,"requires":"references.view"},"references.create":{"label":"Создание конструкций","group":"Образцы","scoped":False,"requires":"references.view"},"references.edit":{"label":"Редактирование конструкций","group":"Образцы","scoped":False,"requires":"references.view"},"references.sides":{"label":"Назначение сторон","group":"Образцы","scoped":False,"requires":"references.view"},"references.delete_file":{"label":"Удаление фотографий","group":"Образцы","scoped":False,"requires":"references.view"},"references.delete":{"label":"Удаление конструкций","group":"Образцы","scoped":False,"requires":"references.view"},"references.region":{"label":"Создание регионов","group":"Образцы","scoped":False,"requires":"references.view"},"queue.view":{"label":"Просмотр задач","group":"Очередь","scoped":True},"queue.detail":{"label":"Подробности задач","group":"Очередь","scoped":True,"requires":"queue.view"},"queue.stop":{"label":"Отмена обработки","group":"Очередь","scoped":True,"requires":"queue.view"},"queue.shared":{"label":"Просмотр общих задач","group":"Очередь","scoped":False},"queue.preparation":{"label":"Остановка, повтор и пропуск подготовки","group":"Очередь","scoped":False},"logs.view":{"label":"Просмотр журналов обработки","group":"Логи","scoped":True},"logs.usage":{"label":"Объём служебных журналов","group":"Логи","scoped":False},"storage.view":{"label":"Просмотр общего хранилища","group":"Хранилище","scoped":False},"storage.diagnostics":{"label":"Расширенная диагностика","group":"Хранилище","scoped":False},"storage.report":{"label":"Скачивание диагностических отчётов","group":"Хранилище","scoped":False},"storage.check":{"label":"Запуск сверок","group":"Хранилище","scoped":False},"storage.limits":{"label":"Просмотр общих лимитов","group":"Хранилище","scoped":False},"storage.configure":{"label":"Изменение общих лимитов","group":"Хранилище","scoped":False},"storage.maintenance":{"label":"Обслуживание хранилища","group":"Хранилище","scoped":False},"system.status":{"label":"Состояние сервера","group":"Система","scoped":False},"system.models":{"label":"Информация о моделях","group":"Система","scoped":False},"system.download_model":{"label":"Загрузка модели","group":"Система","scoped":False},"system.processing":{"label":"Общие настройки сортировки","group":"Система","scoped":False},"system.performance":{"label":"Настройки производительности","group":"Система","scoped":False},"system.retention_view":{"label":"Просмотр сроков хранения","group":"Система","scoped":False},"system.retention":{"label":"Изменение сроков хранения","group":"Система","scoped":False},"system.update_status":{"label":"Состояние обновления","group":"Система","scoped":False},"system.update":{"label":"Обновление MAP","group":"Система","scoped":False},"accounts.view":{"label":"Просмотр аккаунтов","group":"Аккаунты","scoped":False},"accounts.storage":{"label":"Просмотр объёма аккаунтов","group":"Аккаунты","scoped":False},"accounts.requests":{"label":"Просмотр заявок","group":"Аккаунты","scoped":False},"accounts.registration":{"label":"Настройки регистрации","group":"Аккаунты","scoped":False},"accounts.roles":{"label":"Просмотр ролей","group":"Аккаунты","scoped":False},"accounts.history":{"label":"История административных действий","group":"Аккаунты","scoped":False},"accounts.block":{"label":"Блокировка аккаунтов","group":"Аккаунты","scoped":False},"accounts.password":{"label":"Сброс паролей","group":"Аккаунты","scoped":False},"accounts.sessions":{"label":"Просмотр чужих сессий","group":"Аккаунты","scoped":False},"accounts.revoke":{"label":"Завершение чужих сессий","group":"Аккаунты","scoped":False}})
CATALOG.update({"accounts.create":{"label":"Создание аккаунтов","group":"Аккаунты","scoped":False},"accounts.approve":{"label":"Рассмотрение заявок","group":"Аккаунты","scoped":False},"accounts.edit":{"label":"Редактирование имени аккаунта","group":"Аккаунты","scoped":False},"accounts.assign":{"label":"Назначение ролей","group":"Аккаунты","scoped":False},"accounts.overrides":{"label":"Индивидуальные разрешения","group":"Аккаунты","scoped":False},"accounts.role_edit":{"label":"Создание и редактирование ролей","group":"Аккаунты","scoped":False},"accounts.role_delete":{"label":"Удаление ролей","group":"Аккаунты","scoped":False},"accounts.quota":{"label":"Управление личной квотой","group":"Аккаунты","scoped":False},"accounts.grants":{"label":"Выдача доступа к отдельным отчётам","group":"Аккаунты","scoped":False}})
for key in ("results.view","results.media","results.zip"):CATALOG[key]["scoped"]=True
LEVELS=("none","own","all","granted")
LEGACY={key:"granted" for key in ("results.view","results.media","results.zip")}

def validate(values):
    if not isinstance(values,dict) or any(k not in CATALOG or v not in (LEVELS if k.startswith('results.') else ('none','own','all') if CATALOG[k].get('scoped') else ('none','all')) for k,v in values.items()):
        raise HTTPException(422,"Неизвестное разрешение или уровень доступа")
    return dict(values)

def effective(role,overrides):
    # Missing or future permissions are denied. Explicit none wins.
    return {key:overrides.get(key,role.get(key,"none")) for key in CATALOG}

def level(user,key):
    if not user or user.get("blocked"):return "none"
    # Compatibility for internal legacy callers; authenticated users always
    # carry the resolved effective permissions.
    return (user.get("permissions",LEGACY if user.get("access_role")=="viewer" else {})).get(key,"none")

def result_allowed(user,action,*,own,granted):
    return allowed_for(level(user,"results.view"),own=own,granted=granted) and allowed_for(level(user,action),own=own,granted=granted)


def has(user,key):
    if user and user.get("username")=="admin" and user.get("access_role")=="owner":return True
    return level(user,key)!="none"

CATALOG.update({
    "accounts.transfer":{"label":"Передача данных аккаунтов","group":"Аккаунты","scoped":False},
    "accounts.delete":{"label":"Удаление аккаунтов","group":"Аккаунты","scoped":False},
})

CATALOG.update({
    "system.processing_view":{"label":"Просмотр настроек сортировки","group":"Система","scoped":False},
    "system.performance_view":{"label":"Просмотр настроек производительности","group":"Система","scoped":False},
    "references.download":{"label":"Просмотр полноразмерных образцов","group":"Образцы","scoped":False,"requires":"references.view"}
})
CATALOG["photos.process"]["label"]="Первый запуск обработки"
CATALOG["photos.reprocess"]={"label":"Повторная обработка","group":"Фотографии","scoped":True,"requires":"photos.view"}
for action,dependency in {"storage.diagnostics":"storage.view","storage.report":"storage.diagnostics","storage.check":"storage.diagnostics","storage.configure":"storage.limits","system.processing":"system.processing_view","system.performance":"system.performance_view","system.retention":"system.retention_view","system.update":"system.update_status","system.download_model":"system.models"}.items():
    CATALOG[action]["requires"]=dependency

def delegable(actor,desired):
    return all(may_delegate(key,level(actor,key),value) for key,value in desired.items())
