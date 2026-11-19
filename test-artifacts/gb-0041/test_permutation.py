"""换位检验引擎单元测试：暴力枚举 oracle 对照、分批确定性、停算条件、大轴承数抽样。

运行：cd backend && python -m pytest ../test-artifacts/gb-0041/test_permutation.py -q
"""
import itertools,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'backend'))
from src.services import permutation

F1,F2='轴承磨损','转子偏心'
def make_pairs():
    """8个样本、4个轴承；A侧两类故障零漏判，B侧各漏2件，实测最大漏判差为2。"""
    rows=[('S1','B1',F1,F1,'正常'),('S2','B1',F1,F1,F1),
          ('S3','B2',F2,F2,'正常'),('S4','B2',F2,F2,F2),
          ('S5','B3',F1,F1,'正常'),('S6','B3','正常','正常','正常'),
          ('S7','B4',F2,F2,'正常'),('S8','B4',F1,F1,F1)]
    return [{'reference':r,'bearing':b,'actual':a,'pred_a':pa,'pred_b':pb} for r,b,a,pa,pb in rows]
def oracle(pairs,fault_a=F1,fault_b=F2):
    """独立暴力实现：枚举全部换位集，直接重算两侧漏判件数。"""
    bearings=sorted({p['bearing'] for p in pairs})
    def stat(swapped):
        diff=[]
        for f in (fault_a,fault_b):
            ma=mb=0
            for p in pairs:
                pa,pb=(p['pred_b'],p['pred_a']) if p['bearing'] in swapped else (p['pred_a'],p['pred_b'])
                if p['actual']==f and pa!=f:ma+=1
                if p['actual']==f and pb!=f:mb+=1
            diff.append(ma-mb)
        return max(abs(diff[0]),abs(diff[1]))
    observed=stat(set())
    hits=sum(1 for mask in range(1<<len(bearings)) if stat({bearings[i] for i in range(len(bearings)) if mask>>i&1})>=observed)
    return observed,hits,1<<len(bearings)
def evaluate_all(prepared,seed=7):
    total=prepared['total_swaps'];rows=prepared['batch_rows']
    return sum(permutation.evaluate_batch(prepared,seed,i) for i in range((total+rows-1)//rows))
def test_statistic_matches_oracle():
    pairs=make_pairs();prepared=permutation.build_prepared(pairs,F1,F2,200000)
    observed,hits,total=oracle(pairs)
    assert prepared['observed']==observed==2
    assert prepared['misses']=={'a':{F1:0,F2:0},'b':{F1:2,F2:2}}
    assert prepared['mode']=='exact' and prepared['total_swaps']==total==16
    assert evaluate_all(prepared)==hits==12
def test_oracle_randomized():
    import random
    rng=random.Random(11)
    for trial in range(30):
        labels=[F1,F2,'正常'];pairs=[]
        for i in range(rng.randrange(4,14)):
            actual=rng.choice(labels)
            pairs.append({'reference':f'R{i}','bearing':f'B{rng.randrange(5)}','actual':actual,
                          'pred_a':rng.choice(labels),'pred_b':rng.choice(labels)})
        prepared=permutation.build_prepared(pairs,F1,F2,200000)
        prepared['batch_rows']=3  # 强制多批
        observed,hits,total=oracle(pairs)
        assert prepared['observed']==observed,(trial,prepared['observed'],observed)
        assert prepared['total_swaps']==total
        assert evaluate_all(prepared,seed=trial)==hits,(trial,'分批合计与暴力枚举不一致')
def test_batch_determinism_and_retry():
    pairs=make_pairs();prepared=permutation.build_prepared(pairs,F1,F2,200000)
    prepared['batch_rows']=5
    first=[permutation.evaluate_batch(prepared,9,i) for i in range(4)]
    second=[permutation.evaluate_batch(prepared,9,i) for i in range(4)]
    assert first==second,'同一批重算结果必须一致（重试不重复计数）'
    assert sum(first)==evaluate_all(prepared,9)
    assert permutation.evaluate_batch(prepared,9,4)==0,'越界批次不计数'
def test_sampled_mode_large_bearings():
    pairs=[{'reference':f'R{i}','bearing':f'B{i//2}','actual':F1 if i%3 else F2,
            'pred_a':F1 if i%4 else '正常','pred_b':'正常' if i%5 else F2} for i in range(240)]
    prepared=permutation.build_prepared(pairs,F1,F2,200000)
    assert prepared['bearing_count']==120 and prepared['mode']=='sampled'
    assert prepared['total_swaps']==200000
    assert prepared['batch_rows']==min(65536,permutation.CELL_CAP//120),'内存受限时按单元格上限分批'
    hits=evaluate_all(prepared,seed=20261101)
    assert 1<=hits<=200000,'抽样首批含实测换位本身，命中至少为1'
    again=evaluate_all(prepared,seed=20261101)
    assert hits==again,'同种子分批抽样完全确定'
def test_sampled_includes_identity():
    pairs=make_pairs();prepared=permutation.build_prepared(pairs,F1,F2,200000)
    prepared['mode']='sampled';prepared['total_swaps']=10000
    assert permutation.evaluate_batch(prepared,3,0)>=1
def test_exact_when_space_within_samples():
    pairs=[{'reference':f'R{i}','bearing':f'B{i}','actual':F1,'pred_a':F1,'pred_b':'正常'} for i in range(22)]
    prepared=permutation.build_prepared(pairs,F1,F2,5_000_000)
    assert prepared['mode']=='exact' and prepared['total_swaps']==1<<22
def test_pair_rows_stop_conditions():
    a=[{'reference':'S1','actual':F1,'predicted':F1},{'reference':'S2','actual':F2,'predicted':F2}]
    b=[{'reference':'S1','actual':F1,'predicted':F1},{'reference':'S2','actual':F2,'predicted':'正常'}]
    mapping={'S1':'B1','S2':'B1'}
    pairs=permutation.pair_rows(a,b,mapping,F1,F2,1)
    assert [p['bearing'] for p in pairs]==['B1','B1']
    bad=[dict(r,actual='正常') if r['reference']=='S2' else r for r in b]
    try:permutation.pair_rows(a,bad,mapping,F1,F2,1);assert False
    except ValueError as e:assert '真值不符' in str(e)
    try:permutation.pair_rows(a,b,{'S1':'B1'},F1,F2,2);assert False
    except ValueError as e:assert '缺轴承归属' in str(e) and 'v2' in str(e)
    try:permutation.pair_rows(a,b[:1],mapping,F1,F2,1);assert False
    except ValueError as e:assert '样本集合不一致' in str(e)
def test_finish_reports_probability_and_total():
    pairs=make_pairs();prepared=permutation.build_prepared(pairs,F1,F2,200000)
    hits=evaluate_all(prepared)
    result=permutation.finish(prepared,42,hits)
    assert result['probability']==hits/result['total_swaps']
    assert result['total_swaps']==16 and result['mode']=='exact'
    _,expected,_=oracle(pairs)
    assert result['probability']==expected/16
