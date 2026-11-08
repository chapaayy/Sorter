/** Eight saved-output tabs; no processing or model inference from navigation. */
export type ResultView='sam'|'group'|'final'|'screens'|'visual-groups'|'ads'|'ocr'|'comparisons'
export const resultViews:readonly ResultView[]=['sam','group','final','screens','visual-groups','ads','ocr','comparisons']
export const isResultView=(value:unknown):value is ResultView=>
  typeof value==='string'&&resultViews.includes(value as ResultView)
