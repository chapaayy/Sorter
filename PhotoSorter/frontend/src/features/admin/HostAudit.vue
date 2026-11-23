<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {systemApi} from '../../api/system'
import {bytes,errorText} from '../../utils/format'
import type {HostAuditReport} from '../../types/api'
import UiButton from '../../components/ui/UiButton.vue'

const report=ref<HostAuditReport|null>(null)
const loading=ref(true),error=ref('')
const scopeLabels:Record<string,string>={
  app:'Файлы MAP (включая базу и контейнеры)',
  app_shared_layer:'Слои образов, используемых MAP',
  shared_unattributed:'Общие файлы Docker и системы',
  runtime_view:'Временные каталоги контейнеров (только просмотр)'
}
const categoryLabels:Record<string,string>={
  originals:'Оригиналы ФО',normalized:'Перекодированные ФО',
  results_zip:'ZIP результатов',results_temporary:'Временные файлы результатов',
  results:'Результаты',
  reference_objects:'Объекты образцов',reference_uploads:'Загрузка образцов',
  reference_gallery:'Галерея образцов',
  reference_zip:'ZIP образцов',reference_export_temporary:'Временные ZIP образцов',
  megaloc_cache:'Признаки MegaLoc',
  thumbnails:'Миниатюры',other_cache:'Прочий кэш',
  run_logs:'Журналы ФО',run_metadata:'Служебные данные обработок',
  incomplete_uploads:'Незавершённые загрузки',
  docker_volume:'Тома PostgreSQL / Caddy / MAP',
  container_writable_layer:'Записи внутри контейнеров',
  container_metadata_and_logs:'Контейнеры и Docker-логи',
  docker_image_layer:'Слои образов MAP',
  docker_other:'Другие Docker-файлы и BuildKit',
  container_tmp:'Временные каталоги /tmp (вид внутри контейнера)',
  container_root_mount:'Подключённая файловая система контейнера (не суммируется)',
  open_deleted_file:'Удалённые файлы, ещё открытые процессом',
  model_weights:'Веса моделей',model_cache:'Кэши моделей',
  app_source_installer_and_git:'Приложение, установщик и Git',
  audit_reports:'Отчёты аудита'
}
const scopes=computed(()=>Object.entries(report.value?.scopes||{})
  .sort((a,b)=>b[1].allocated_bytes-a[1].allocated_bytes))
const categories=computed(()=>Object.entries(report.value?.categories||{})
  .sort((a,b)=>b[1].allocated_bytes-a[1].allocated_bytes))
async function refresh(){
  loading.value=true;error.value=''
  try{report.value=await systemApi.hostAudit()}
  catch(e){error.value=errorText(e)}
  finally{loading.value=false}
}
onMounted(()=>{void refresh()})
</script>

<template>
  <section class="panel stack" aria-label="Полный аудит сервера">
    <div class="row between wrap">
      <div class="stack" style="gap:4px">
        <h2>Аудит всего сервера MAP</h2>
        <p class="meta">Файлы приложения, PostgreSQL и Caddy, Docker, слои и кэш сборки,
          временные каталоги контейнеров, системные журналы. Только чтение.</p>
      </div>
      <UiButton :loading="loading" @click="refresh">Обновить отчёт</UiButton>
    </div>
    <p v-if="error" role="alert" class="meta">{{error}}</p>
    <template v-if="report?.available">
      <div class="row wrap">
        <strong>Записей: {{(report.files_scanned||0).toLocaleString('ru-RU')}}</strong>
        <strong>Учтено блоков: {{bytes(report.allocated_bytes||0)}}</strong>
      </div>
      <p class="meta">Снимок: {{report.captured_at}}.
        Проверка: {{report.scan_seconds}} с. Пропущено: {{report.skipped_paths}}.
        Общие файлы ОС не считаются собственностью MAP.
        Подключённые представления контейнеров не суммируются повторно.
        Исключено таких представлений: {{report.container_root_mounts_excluded??0}}.</p>
      <div class="row wrap">
        <a v-if="report.csv_available" class="btn secondary"
          href="/api/storage/host-audit/report.csv" download="map-full-host-file-audit.csv">
          Скачать полный аудит сервера CSV
        </a>
        <a v-if="report.csv_available" class="btn secondary"
          href="/api/storage/host-audit/report.json" download="map-full-host-audit-summary.json">
          Скачать сводку и ошибки JSON
        </a>
        <a v-if="report.write_sites_available" class="btn secondary"
          href="/api/storage/host-audit/write-sites.csv" download="map-file-write-sites.csv">
          Скачать карту записей файлов в коде
        </a>
      </div>
      <p v-if="report.write_sites_available" class="meta">
        Найдено потенциальных мест создания или изменения файлов в исходниках:
        {{report.write_sites_count}}. Это дополнение к снимку диска, а не история операций.
      </p>
      <h3>Каким областям принадлежит место</h3>
      <div v-for="[key,stat] in scopes" :key="key" class="row between wrap audit-row">
        <div><strong>{{scopeLabels[key]||key}}</strong>
          <div class="meta">{{stat.files.toLocaleString('ru-RU')}} записей</div></div>
        <strong>{{bytes(stat.allocated_bytes)}}</strong>
      </div>
      <details>
        <summary>Все категории файлов</summary>
        <div v-for="[key,stat] in categories" :key="key" class="row between wrap audit-row">
          <span>{{categoryLabels[key]||key}} ({{stat.files}})</span>
          <strong>{{bytes(stat.allocated_bytes)}}</strong>
        </div>
      </details>
      <p v-if="report.errors?.length" role="status" class="meta">
        При проверке обнаружены недоступные области или неопределённые зависимости:
        {{report.errors.length}}. Смотри подробности в отчёте.
      </p>
      <details v-if="report.errors?.length">
        <summary>Ошибки и предупреждения проверки</summary>
        <ul><li v-for="(item,index) in report.errors" :key="index">{{item}}</li></ul>
      </details>
      <p class="meta">Это снимок файлов на диске. Файлы, которые были созданы и удалены
        до проверки, нельзя увидеть задним числом. Для них потребуется отдельный
        непрерывный журнал событий. Ничего не очищается.</p>
    </template>
    <p v-else-if="!loading" class="meta">Серверный аудит ещё не выполнялся.
      Первая проверка запускается на VPS с правами администратора.</p>
    <details>
      <summary>Команда запуска полной проверки на VPS</summary>
      <p class="meta">Нужны права root: Docker-тома и временные файлы контейнеров не доступны
        обычному пользователю сайта. Команда только читает файлы и создаёт CSV-отчёт.</p>
      <code class="command">cd /opt/Sorter &amp;&amp; sudo python3 PhotoSorter/tools/maintenance/audit_host.py --project-root /opt/Sorter</code>
      <p class="meta">После выполнения нажми «Обновить отчёт».</p>
    </details>
  </section>
</template>

<style scoped>
.audit-row{padding:9px 0;border-bottom:1px solid var(--border-subtle);gap:12px}
.command{display:block;overflow-wrap:anywhere;white-space:normal;user-select:text;font-size:12px;padding:12px;background:var(--panel-alt);border-radius:8px}
details{font-size:13px}
</style>
