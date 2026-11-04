"""Stage 2.6 preserves the successful one-threshold MegaLoc clustering."""
from pathlib import Path
from collections import Counter
import numpy as np
import pytest
from PIL import Image
from app.recognition.grouping.finder import find_groups
from app.recognition.pipeline import match_grouped_megaloc

def vector(degrees):
    radians=np.deg2rad(degrees)
    return np.array([np.cos(radians),np.sin(radians)],dtype=np.float32)

def test_threshold_components_and_chain():
    images=[Path(f'fo_{i}.jpg') for i in range(3)]
    groups=find_groups(images,[vector(0),vector(20),vector(45)])
    assert len(groups)==1 and groups[0].members==(0,1,2)
    assert groups[0].min_similarity==pytest.approx(np.cos(np.deg2rad(45)),abs=1e-5)
    assert groups[0].peers[0][0][0]==1

@pytest.mark.parametrize('threshold,expected',[(0.50,1),(0.80,1),(0.90,2)])
def test_single_threshold_and_no_extra_filters(threshold,expected):
    images=[Path(f'{i}.jpeg') for i in range(2)]
    assert len(find_groups(images,[vector(0),vector(30)],cosine_threshold=threshold))==expected

@pytest.mark.parametrize('threshold',[0.3,1.0,np.nan,np.inf])
def test_invalid_threshold(threshold):
    with pytest.raises(ValueError):find_groups([Path('a')],[vector(0)],cosine_threshold=threshold)

def test_groups_stable_and_independent_of_photo_files(tmp_path):
    paths=[tmp_path/f'does-not-exist-{i}.jpg' for i in range(4)]
    result=find_groups(paths,[vector(0),vector(20),vector(90),vector(110)])
    assert [(g.id,g.members) for g in result]==[('G0001',(0,1)),('G0002',(2,3))]
    assert result[0].nearest_other_group=='G0002'

def test_grouping_before_reference_and_once_per_file(tmp_path):
    fo=[tmp_path/f'q{i}.jpg' for i in range(3)]
    sample=tmp_path/'sample.jpg'
    for item in [*fo,sample]:Image.new('RGB',(36,36),'red').save(item)
    class Engine:
        def __init__(self):self.events=[];self.calls=Counter()
        def extract(self,path):
            self.events.append(('extract',str(path)))
            self.calls[str(path)]+=1
            return vector(90 if Path(path)==fo[2] else 0)
    engine=Engine()
    def progress(stage,done,total,detail):engine.events.append(('progress',stage))
    rows=match_grouped_megaloc(engine,[(sample,'SAM-1000')],fo,progress=progress,cosine_threshold=.50)
    assert [r['group_id'] for r in rows]==['G0001','G0001','G0002']
    assert all(count==1 for count in engine.calls.values())
    assert engine.events.index(('extract',str(sample)))>engine.events.index(('progress','grouping_diagnostics'))
    assert rows[0]['top'][0]['label']=='SAM-1000'

def test_multiple_groups_can_share_one_sam(tmp_path):
    first=[tmp_path/f'fo_{i}.jpg' for i in range(4)]
    refs=[(tmp_path/'ref_1.jpg','SAM-0004'),(tmp_path/'ref_2.jpg','SAM-0004')]
    known={str(first[0]):vector(0),str(first[1]):vector(0),str(first[2]):vector(90),str(first[3]):vector(90),str(refs[0][0]):vector(0),str(refs[1][0]):vector(90)}
    class Engine:
        def extract(self,path):return known[str(path)]
    rows=match_grouped_megaloc(Engine(),refs,first,cosine_threshold=.50)
    assert [r['group_id'] for r in rows]==['G0001','G0001','G0002','G0002']
    assert set(r['top'][0]['label'] for r in rows)=={'SAM-0004'}
    assert [r['individual_sam'] for r in rows]==['SAM-0004']*4

def test_1800_fo_grouping_does_not_run_model():
    paths=[Path(f'fo{i:04d}.jpg') for i in range(1800)]
    features=[np.array([1.,0.,0.],dtype=np.float32)]*600+[np.array([0.,1.,0.],dtype=np.float32)]*600+[np.array([0.,0.,1.],dtype=np.float32)]*600
    groups=find_groups(paths,features,cosine_threshold=.50)
    assert [len(g.members) for g in groups]==[600,600,600]
    assert len(groups[0].peers[0])==20
