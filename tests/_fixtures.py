"""Explicit confirmed-device preconditions for tests whose subject is later control logic."""
from copy import deepcopy
import portable_server as app

def confirmed(b):
    b.clear_comparison()
    b.model_id='32u-2026';b.model_confirmed=True
    b.device_model={'verified':True,'model_id':'32u-2026'}
    b.initial_backup={'ready':True};b.backup_policy={'pc':True,'device':False,'confirmed':True}
    b.model_monitor=None
    for name,value in {'telemetry':{'hdr_revision':2},'model_detection':{'monitors':[]},'nit_references':[],
                       'ui_preferences':dict(app.DEFAULT_UI),'config_saved_at':'',
                       'budget_value':24,'pattern_config':dict(app.PATTERN),
                       'native_abl':dict(app.ABL_DEFAULT),'calibration':dict(app.CALIBRATION)}.items():
        if not hasattr(b,name):setattr(b,name,deepcopy(value))
    return b
