"""Feed media to the existing photo pipeline without letting frames bridge FO groups."""
from collections import Counter
from pathlib import Path

from app.config import DATA_DIR
from app.recognition.grouping.finder import PhotoGroup, find_groups
from app.recognition.errors import JobCancelled
from ..database import connect
from ..storage.paths import owned_file,batch_root
from .formats import output_name
from .video import extract_frames


class MediaQueries:
    def __init__(self, job, directory):
        self.videos = {}
        self.information = {}
        self.photos = []
        self.frame_paths = []
        self.errors = 0
        batch_id = job.info['batch_id']
        root = batch_root(batch_id)
        with connect() as db:
            rows = db.execute("""SELECT u.id,u.filename,u.target_path,u.original_media_type,
                u.media_action,u.media_output_path,u.media_duration,b.media_image_format,b.media_video_format
                FROM uploads u JOIN batches b ON b.id=u.batch_id
                WHERE u.batch_id=%s AND u.kind='fo' AND u.finalized ORDER BY u.created_at,u.id""",
                (batch_id,)).fetchall()
        has_videos = any((row['original_media_type'] or '').startswith('video/') for row in rows)
        if has_videos:job.progress(None,'media_inputs',0,len(rows),'Подготовка входных файлов')
        for i,row in enumerate(rows,1):
            if job.stopped():raise JobCancelled('Остановлено пользователем')
            self._add(job,row,root,directory)
            if has_videos:job.progress(None,'media_inputs',i,len(rows),'Подготовка входных файлов')

    def _add(self, job, row, root, directory):
        video = (row['original_media_type'] or '').startswith('video/')
        path = row['media_output_path'] or (row['target_path'] if row['media_action']=='keep' else None)
        if not path:
            self.errors += 1
            return
        source = owned_file(Path(path),root)
        try:
            if not source.is_file():raise FileNotFoundError()
            if video:
                folder = directory / str(row['id'])
                folder.mkdir()
                frames = extract_frames(source,folder,stop=job.stopped)
                self.frame_paths.extend(frames)
                self.videos[str(source)] = [str(frame) for frame in frames], None
            else:
                self.photos.append(source)
        except InterruptedError as exc:
            raise JobCancelled('Остановлено пользователем') from exc
        except (OSError, ValueError) as exc:
            failed = ('Не удалось извлечь кадры видео' if video else 'Файл подготовки недоступен')
            job.log('WARNING',row['filename']+': '+failed)
            if not source.is_file():
                self.errors += 1
                return
            self.videos[str(source)] = [], failed
        ext = row['media_video_format' if video else 'media_image_format']
        self.information[str(source)] = {'export_name':output_name(row['filename'],ext),
            'media_kind':'video' if video else 'image','duration':row['media_duration'],
            'upload_id':str(row['id'])}

    def grouping(self, paths, vectors, **kwargs):
        known_frames = set(self.frame_paths)
        photos = [i for i,path in enumerate(paths) if path not in known_frames]
        # Pipeline orders real photos before frames, so the photo groups and
        # their peer indices are unchanged relative to an image-only run.
        assert photos == list(range(len(photos)))
        groups = find_groups(paths[:len(photos)],vectors[:len(photos)],**kwargs)
        return [*groups, *(PhotoGroup('video-frame-'+str(i),(i,)) for i in range(len(photos),len(paths)))]

    def collapse(self, rows):
        lookup = {row['query']:row for row in rows}
        images = [{**lookup[str(p)],**self.information[str(p)]} for p in self.photos]
        return images + [{**video_vote(path, [lookup.get(frame,{}) for frame in frames], error),
                          **self.information[path]} for path,(frames,error) in self.videos.items()]


def video_vote(path, frames, error=None):
    """Require repeated evidence, never assign a conflicting video to two SAMs."""
    row = {'query':path,'top':[],'group_id':None,'reason':error}
    if error:return row
    votes = []
    for frame in frames:
        top = frame.get('individual_top') or frame.get('top') or []
        if not top:continue
        # Compare nearest two constructions; scores are similarities, not probabilities.
        if len(top)>1 and top[0]['score']-top[1]['score'] < .015:continue
        votes.append(top[0])
    counts = Counter(vote['label'] for vote in votes)
    if len(counts)!=1 or len(votes)<max(2,(2*len(frames)+2)//3):
        row['reason'] = 'Кадры указывают на разные конструкции' if len(counts)>1 else 'Недостаточно согласованных кадров'
        return row
    winner = max(votes,key=lambda vote:vote['score'])
    row['top'] = [{**winner,'score':round(sum(v['score'] for v in votes)/len(votes),6)}]
    return row
