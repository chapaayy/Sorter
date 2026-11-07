<script setup lang="ts">
import type {QueueTask} from '../../types/workQueue'
import {STATE_RU,hasBlockingFailure,duration,isPrep} from '../../utils/queuePresentation'
import {date} from '../../utils/format'
import UiButton from '../../components/ui/UiButton.vue'
const props=defineProps<{task:QueueTask;position?:number;busy?:boolean}>()
const emit=defineEmits<{
 (e:'action',task:QueueTask,kind:'stop'|'retry'|'skip'):void
 (e:'details',task:QueueTask):void
}>()
const canStop=()=>props.task.state==='running' || props.task.state==='queued'
</script>
<template>
<article class="queue-task-row">
  <span class="processing-queue-position" :aria-label="'Номер в очереди '+(position||task.seq)">
    {{position||task.seq}}
  </span>
  <div class="queue-task-main">
    <div class="row wrap" style="gap:8px">
      <strong>{{isPrep(task)?'Подготовка образцов':task.batch_name||'Фотоотчёт'}}</strong>
      <span class="status" :class="{'danger':hasBlockingFailure(task),'ok':task.state==='completed'}">
        {{STATE_RU[task.state]}}
      </span>
    </div>
    <span class="meta">{{isPrep(task)?'Образцы · отдельное задание':'ФО · обработка'}}
      · добавлено {{date(task.created_at)}} · длительность {{duration(task)}}
    </span>
    <span v-if="isPrep(task)" class="meta">
      Готово {{task.completed_count||0}}/{{task.total_count||0}}
      <template v-if="task.failed_count"> · ошибок: {{task.failed_count}}</template>
      <template v-if="task.stop_requested&&task.state==='running'"> · запрошена остановка</template>
    </span>
    <span v-if="task.error" class="meta queue-task-error">{{task.error}}</span>
    <div v-if="isPrep(task)&&task.total_count" class="progress-track" role="progressbar"
      :aria-valuemin="0" :aria-valuemax="task.total_count||0" :aria-valuenow="task.completed_count||0">
      <span class="progress-fill" :style="{width:Math.min(100,100*(task.completed_count||0)/(task.total_count||1))+'%'}"/>
    </div>
  </div>
  <div class="row wrap queue-task-actions">
    <UiButton v-if="isPrep(task)" small @click="emit('details',task)">Подробности</UiButton>
    <RouterLink v-else-if="task.fo_run_id" class="btn small" :to="'/processing/'+task.fo_run_id">
      Обработка
    </RouterLink>
    <UiButton v-if="hasBlockingFailure(task)" small :disabled="busy"
      @click="emit('action',task,'retry')">Повторить</UiButton>
    <UiButton v-if="isPrep(task)&&hasBlockingFailure(task)" small :disabled="busy"
      @click="emit('action',task,'skip')">Пропустить</UiButton>
    <UiButton v-if="canStop()" small :disabled="busy||!!task.stop_requested"
      @click="emit('action',task,isPrep(task)&&task.state==='queued'?'skip':'stop')">
      {{task.state==='queued'?'Убрать':'Остановить'}}
    </UiButton>
  </div>
</article>
</template>
