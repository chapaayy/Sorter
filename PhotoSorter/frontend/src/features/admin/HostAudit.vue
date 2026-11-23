<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {systemApi} from '../../api/system'
import {bytes,errorText} from '../../utils/format'
import type {HostAuditReport,LiveAuditStatus} from '../../types/api'
import UiButton from '../../components/ui/UiButton.vue'

const report=ref<HostAuditReport|null>(null)
const live=ref<LiveAuditStatus|null>(null)
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
  containerd_active_upper:'Слои записи запущенных контейнеров MAP',
  containerd_shared_image_layer:'Общие слои образов, используемых MAP',
  containerd_unattributed:'Слои containerd без подтверждённой принадлежности',
  containerd_content_or_metadata:'Данные и кэш containerd без подтверждённой принадлежности',
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
  try{
    const [hostResult,liveResult]=await Promise.allSettled([systemApi.hostAudit(),systemApi.liveAudit()])
    if(hostResult.status==='fulfilled')report.value=hostResult.value
    else error.value=errorText(hostResult.reason)
    if(liveResult.status==='fulfilled')live.value=liveResult.value
    else live.value={available:false,detail:'Состояние наблюдателя недоступно'}
  }catch(e){error.value=errorText(e)}
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
      <h3>Слои containerd: принадлежность</h3>
      <p class="meta">
        Подтверждённых снимков: {{report.containerd_attribution?.matched_snapshots??0}}.
        Ссылок из работающих контейнеров: {{report.containerd_attribution?.container_mount_references??0}}.
        Уникальных цепочек слоёв образов: {{report.containerd_attribution?.image_chains_checked??0}};
        подтверждено ключей через ctr: {{report.containerd_attribution?.ctr_snapshot_metadata_checked
          ? report.containerd_attribution?.image_chains_matched : 'не проверено'}}.
      </p>
      <p class="meta">Слои общих образов не считаются исключительной собственностью MAP.
        Нераспознанные данные containerd остаются в отдельной категории, а не исчезают из отчёта.</p>
      <details v-if="report.containerd_attribution?.warnings?.length">
        <summary>Пробелы сопоставления containerd ({{report.containerd_attribution.warnings.length}})</summary>
        <ul><li v-for="(item,index) in report.containerd_attribution.warnings" :key="index">{{item}}</li></ul>
      </details>
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
    <div class="stack" style="gap:8px" aria-label="Непрерывный учёт файлов">
      <h3>Непрерывный учёт файловых событий</h3>
      <p v-if="!live?.available" class="meta">
        Наблюдатель ещё не запускался. Он устанавливается как системная служба при обновлении MAP от root.
      </p>
      <template v-else>
        <p class="meta">
          Состояние: <strong>{{live.running?'Работает по последнему отчёту':'Остановлен'}}</strong>.
          Записей журнала: {{(live.events||0).toLocaleString('ru-RU')}}.
          Событий с учётом группировки: {{(live.events_observed_including_aggregates??live.events??0).toLocaleString('ru-RU')}}.
          Каталогов под наблюдением: {{(live.watched_directories||0).toLocaleString('ru-RU')}}.
          Переполнений очереди: {{live.queue_overflows||0}}.
          Ошибок наблюдения: {{live.watch_errors||0}}.
          Повторных закрытий общей памяти PostgreSQL: {{(live.postgres_shm_close_writes_aggregated||0).toLocaleString('ru-RU')}}.
          Последний сигнал: {{live.heartbeat_at||'неизвестно'}}.
        </p>
        <a v-if="live.download_available" class="btn secondary"
          href="/api/storage/host-audit/live-events.jsonl"
          download="map-file-live-events.jsonl">Скачать все события файлов JSONL</a>
        <details v-if="live.warnings?.length">
          <summary>Ошибки наблюдения ({{live.warnings.length}})</summary>
          <ul><li v-for="(item,index) in live.warnings" :key="index">{{item}}</li></ul>
        </details>
      </template>
      <p class="meta">Фиксируются создание, закрытие после записи, переименование и удаление.
        Неназванные временные файлы и события до запуска службы не восстановить.
        Пропуски и переполнение очереди фиксируются, но не скрываются.</p>
    </div>
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
