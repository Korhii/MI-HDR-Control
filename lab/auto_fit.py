"""Validate automatic plans against the measured offline recipe set, never arbitrary targets."""
AUTO_KNOTS=[0,.001,.01,.1,.5,1,2,5,10,25,50,75,100]

def validate_plan(data,level,path):
    # Saved full profile values remain authoritative. A new process refits before
    # applying; transient algorithm-result tokens are never imported as writes.
    raise ValueError('自动拟合令牌仅本次会话有效，请重建预览；已保存的完整手动参数不受影响')

def validate_preview(data):
    import math
    if data['mode']!='global' or type(data['ceiling']) is not int or not 0<=data['ceiling']<=86:raise ValueError('自动预览模式/上限错误')
    targets=data['targets']
    if len(targets)==2 and all(len(row)==9 for row in targets):targets=[row[:6]+[row[5]+(row[6]-row[5])*15/40]+row[6:] for row in targets]
    if len(targets)==2 and all(len(row)==10 for row in targets):
        from firmware_model import interp
        targets=[[interp(list(zip([0,.001,.01,.1,1,10,25,50,75,100],row)),a,True) for a in AUTO_KNOTS] for row in targets]
    if len(targets)!=2 or any(len(row)!=len(AUTO_KNOTS) or any(type(v) not in (int,float) or not math.isfinite(v) or not 0<=v<=10000 for v in row) for row in targets):raise ValueError('目标曲线需要两组13个有限nit值')
    return dict(mode='global',ceiling=data['ceiling'],targets=targets)
