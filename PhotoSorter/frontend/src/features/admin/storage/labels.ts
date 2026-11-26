export const labels:Record<string,string>={
  fo_original:'Оригиналы ФО',fo_normalized:'Перекодированные файлы',result_media:'Результаты',
  result_metadata:'Метаданные результатов',run_state:'Состояние обработок',fo_thumbnail:'Личные миниатюры',
  reference_object:'Общие образцы',reference_gallery:'Галерея образцов',reference_embedding:'Постоянные эмбеддинги MegaLoc',
  reference_thumbnail:'Общие миниатюры',fo_upload_part:'Незавершённые загрузки ФО',reference_upload_part:'Загрузки образцов',
  transcode_temp:'Перекодирование',video_frames:'Кадры видео',processing_staging:'Подготовка результатов',
  fo_embedding_temp:'Временные признаки ФО',zip_results:'ZIP фотоотчётов',zip_construction:'ZIP конструкций',
  zip_references:'ZIP образцов',zip_fragment:'Создаваемые ZIP',archive_lock:'Служебные файлы ZIP',
  atomic_fragment:'Промежуточные файлы',model_download:'Загрузка модели',scratch:'Рабочие временные файлы',
  model_weights:'Веса модели',model_source:'Исходники модели',model_metadata:'Метаданные модели',technical_cache:'Удаляемый технический кэш',
  postgres_data:'PostgreSQL',caddy_state:'Caddy',service_log:'Журналы сервисов',run_log:'Журналы обработок',
  access_log:'Журналы доступа',audit_event:'Журналы аудита',audit_snapshot:'Снимки аудита',updater_backup:'Резервные копии',
  updater_workspace:'Временные файлы обновления',builder_marker:'Состояние сборок',updater_control:'Состояние обновлятора',updater_rpc_socket:'Служебный сокет обновлятора',
  installation_state:'Состояние установки',unknown:'Неизвестные файлы',media_preparation:'Перекодирование ФО',
  fo_processing:'Обработка ФО',reference_preparation:'Подготовка образцов',reference_deletion:'Удаление образцов',
  upload:'Загрузка файлов',download:'Скачивание файлов',archive:'Создание ZIP',transcode:'Перекодирование',model:'Загрузка модели',model_install:'Установка модели'
}
Object.assign(labels,{fo_upload:'Загрузка ФО',reference_upload:'Загрузка образцов',result_export:'Публикация результатов',video_frames:'Кадры видео',frame_index:'Индекс кадров',video_poster:'Кадр для миниатюры',atomic_write:'Атомарная запись'})
export const categoryName=(key:string)=>labels[key]||key
export const groups=[
 {label:'Фотоотчёты',keys:['fo_original','fo_normalized','result_media','result_metadata','run_state','fo_thumbnail']},
 {label:'Образцы',keys:['reference_object','reference_gallery','reference_embedding','reference_thumbnail']},
 {label:'Модели ИИ',keys:['model_weights','model_source','model_metadata','technical_cache']},
 {label:'Временные файлы',keys:['fo_upload_part','reference_upload_part','transcode_temp','video_frames','processing_staging','fo_embedding_temp','zip_results','zip_construction','zip_references','zip_fragment','archive_lock','atomic_fragment','model_download','scratch']},
 {label:'База данных',keys:['postgres_data']},
 {label:'Журналы MAP',keys:['service_log','run_log','access_log','audit_event']},
 {label:'Служебные файлы и инфраструктура',keys:['caddy_state','audit_snapshot','updater_backup','updater_workspace','builder_marker','updater_control','updater_rpc_socket','installation_state']}
]
