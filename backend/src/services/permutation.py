"""漏判差异换位检验：同一轴承的样本整体交换两侧判读，统计两类指定故障的最大漏判件数绝对差。

配对后每个样本对两个故障类型各产生有向漏判差 d∈{-1,0,1}（A侧漏判−B侧漏判）。
轴承 g 的样本求和得 delta_g；换位集合 s 下，故障 f 的两侧漏判差为
    D_f(s) = D_f(0) − 2·Σ_{g∈s} delta_g(f)
统计量 T(s)=max(|D_1(s)|,|D_2(s)|)，概率为 T(s) 达到或超过实测差 T(0) 的换位比例。
轴承不超过20个（或换位空间不大于抽样数）时精确枚举全部换位；否则按固定种子分批随机抽样，
每批内容完全确定，中断恢复与失败重试都不会重复计数。
"""
import numpy as np
EXACT_LIMIT=1<<20
CELL_CAP=2_000_000
ROW_CAP=65536
def pair_rows(rows_a,rows_b,mapping,fault_a,fault_b,version):
    """按样本编号配对两项研究的折外判读；真值不符或缺轴承归属即停算。"""
    if len({r['reference'] for r in rows_a})!=len(rows_a) or len({r['reference'] for r in rows_b})!=len(rows_b):
        raise ValueError('折外判读中存在重复样本编号，无法按样本配对')
    by_a={r['reference']:r for r in rows_a};by_b={r['reference']:r for r in rows_b}
    if set(by_a)!=set(by_b):raise ValueError('两项研究的折外判读样本集合不一致，无法按样本配对')
    pairs=[]
    for reference in sorted(by_a):
        a,b=by_a[reference],by_b[reference]
        if a['actual']!=b['actual']:raise ValueError(f"真值不符：样本 {reference} 两侧真值分别为 {a['actual']} / {b['actual']}，停止计算")
        bearing=str(mapping.get(reference) or '').strip()
        if not bearing:raise ValueError(f'缺轴承归属：样本 {reference} 在归属版本 v{version} 中没有轴承归属，停止计算')
        pairs.append({'reference':reference,'bearing':bearing,'actual':a['actual'],'pred_a':a['predicted'],'pred_b':b['predicted']})
    return pairs
def build_prepared(pairs,fault_a,fault_b,samples):
    """由配对样本汇总各轴承的有向漏判差，决定精确枚举或分批抽样的计算方式。"""
    index={};bearings=[];delta=[]
    misses={'a':{fault_a:0,fault_b:0},'b':{fault_a:0,fault_b:0}}
    for p in pairs:
        slot=index.get(p['bearing'])
        if slot is None:slot=len(bearings);index[p['bearing']]=slot;bearings.append(p['bearing']);delta.append([0,0])
        for side,pred in (('a',p['pred_a']),('b',p['pred_b'])):
            for fi,fault in enumerate((fault_a,fault_b)):
                if p['actual']==fault and pred!=fault:
                    misses[side][fault]+=1
                    delta[slot][fi]+=1 if side=='a' else -1
    d0=[misses['a'][fault_a]-misses['b'][fault_a],misses['a'][fault_b]-misses['b'][fault_b]]
    g=len(bearings)
    if g<=20 or (g<63 and (1<<g)<=samples):mode,total='exact',1<<g
    else:mode,total='sampled',samples
    batch_rows=max(1,min(ROW_CAP,CELL_CAP//max(g,1)))
    return {'faults':[fault_a,fault_b],'bearings':bearings,'delta_a':[d[0] for d in delta],'delta_b':[d[1] for d in delta],
            'd0':d0,'observed':max(abs(d0[0]),abs(d0[1])),'misses':misses,'pairs':len(pairs),'bearing_count':g,
            'mode':mode,'total_swaps':total,'batch_rows':batch_rows}
def _hits(bits,deltas,d0,observed):
    sums=bits@deltas
    return int((np.abs(d0-2*sums).max(axis=1)>=observed).sum())
def evaluate_batch(prepared,seed,batch_index):
    """评估第 batch_index 批换位，返回达到或超过实测差的件数；内容完全确定，重算结果一致。"""
    g=prepared['bearing_count'];rows=prepared['batch_rows'];start=batch_index*rows
    count=min(rows,prepared['total_swaps']-start)
    if count<=0:return 0
    deltas=np.array([prepared['delta_a'],prepared['delta_b']],dtype=np.int64).T
    d0=np.array(prepared['d0'],dtype=np.int64)
    if prepared['mode']=='exact':
        masks=np.arange(start,start+count,dtype=np.uint64)
        bits=((masks[:,None]>>np.arange(g,dtype=np.uint64))&1).astype(np.int8)
    else:
        rng=np.random.default_rng(np.random.SeedSequence([int(seed),int(batch_index)]))
        if batch_index==0:
            head=np.zeros((1,g),dtype=np.int8)
            bits=np.vstack([head,rng.integers(0,2,size=(count-1,g),dtype=np.int8)]) if count>1 else head
        else:bits=rng.integers(0,2,size=(count,g),dtype=np.int8)
    return _hits(bits,deltas,d0,prepared['observed'])
def finish(prepared,seed,hits):
    """同版算齐后汇总概率与换位总数。"""
    total=prepared['total_swaps']
    return {'probability':hits/total,'hits':hits,'total_swaps':total,'observed':prepared['observed'],
            'mode':prepared['mode'],'pairs':prepared['pairs'],'bearings':prepared['bearing_count'],
            'misses':prepared['misses'],'faults':prepared['faults'],'seed':seed,
            'explanation':'同一轴承的样本整体交换两侧判读；概率为换位后两类指定故障最大漏判件数绝对差达到或超过实测差的换位比例。'+('全部换位已精确枚举。' if prepared['mode']=='exact' else '换位空间过大，按固定种子分批随机抽样估计。')}
