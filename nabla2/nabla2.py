# AUTOGENERATED! DO NOT EDIT! File to edit: 01nabla2.ipynb (unless otherwise specified).

__all__ = ['force_list', 'is_listy', 'set_seed', 'format_time', 'ProgressBar', 'DISPLAY_DECIMALS', 'Learner',
           'accuracy']

# Cell
from pathlib import Path
from typing import Any, Union, Tuple, Callable, TypeVar, Generic

import torch
import numpy as np
import pandas as pd
from datetime import datetime
import sys
import json
from collections import defaultdict
import sys
import time

# Cell
def force_list(itm):
    if itm is None:
        return None
    if isinstance(itm,list):
        itm_list = itm
    elif isinstance(itm,tuple):
        itm_list = [it for it in itm]
    else:
        itm_list = [itm,]
    return itm_list

# Cell
def is_listy(x):
    return isinstance(x, (list,tuple))

# Cell
def set_seed(seed_val=0):
    torch.manual_seed(0)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    np.random.seed(0)
    return

# Cell
def _progress(count, total, status='',time_info='',blank=False):
    bar_len = 60
    filled_len = int(round(bar_len * count / float(total)))

    percents = "{}% {}/{}".format(round(100.0 * count / float(total), 1),count,total)
    bar = '#' * filled_len + '-' * (bar_len - filled_len)


    progress_str = '   {status} [{bar}] {percents}  {time_info}   \r'.format(status=status,bar=bar,percents=percents,time_info=time_info)
    if blank:
        progress_str = " "*len(progress_str)+"\r"
    sys.stdout.write(progress_str)
    sys.stdout.flush()

# Cell
def format_time(t):
    t = int(t)
    h,m,s = t//3600, (t//60)%60, t%60
    if h!= 0: return f'{h}:{m:02d}:{s:02d}'
    else:     return f'{m:02d}:{s:02d}'

# Cell
class ProgressBar():
    def __init__(self, iterable, status=None):
        self.iterable = iterable
        self.len = len(iterable)
        self.done = 0
        self.status = status if status is not None else '>'

    def __iter__(self):
        start_t = time.time()

        for i, itm in enumerate(self.iterable):
            yield itm
            elapsed_t = time.time() - start_t
            time_info = "[{}/{}]".format(format_time(elapsed_t),format_time(elapsed_t*self.len/(i+1)))
            _progress(i, self.len, self.status, time_info)
        _progress(i, self.len, self.status,time_info, blank=True)

    def set_status(self, new_status):
        self.status = new_status
        return

# Cell

# constants
DISPLAY_DECIMALS = 3

# Cell
def _set_device(device):
    if device is None:
        return torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    else:
        return device

# Cell
def _prepare_batch(tb, device):
    tb = force_list(tb)
    tb = [t.to(device) if t is not None else None for t in tb]
    return tb

# Cell
def _batch_forward_pass(device, model, xb, yb,  compute_loss, loss_func=None):
    # takes care of multiple input and or multiple output from model.
    xb = _prepare_batch(xb, device)
    pb = model(*xb)

    if compute_loss  and (loss_func is not None):
        yb = _prepare_batch(yb, device)
        loss = loss_func(pb, *yb)
    else:
        loss=None

    return loss, pb

# Cell
def _show_loss_on_progress_bar(ds,loss)-> None:
    if isinstance(ds,ProgressBar):
        if isinstance(loss,(list,tuple)):
            loss_val = loss[0].item()
        else:
            loss_val = loss.item()
        ds.set_status("{:4.2f}".format(loss_val))

# Cell
def _dataset_forward_pass(dataset, model, loss_func, is_train:bool, batch_preprocess_fn, prediction_recorder_fn,
                          loss_pre_process_fn, gradient_post_proces_fn, optimizer, device )->None:
    if is_train:
        model.train()
    else:
        model.eval()

    model = model.to(device)

    for data_batch in dataset:
        with torch.set_grad_enabled(is_train):
            phase = 'train' if is_train==True else 'eval'
            xb, yb = batch_preprocess_fn(data_batch, phase=phase)
            loss, pb = _batch_forward_pass(device, model, xb, yb, compute_loss=True, loss_func=loss_func)
            prediction_recorder_fn(xb,yb,pb,loss,is_train=is_train)
            _show_loss_on_progress_bar(dataset, loss)
            if is_train:
                loss = loss_pre_process_fn(loss)
                loss.backward()
                gradient_post_proces_fn()
                optimizer.step()
                optimizer.zero_grad()

# Cell
class _recorder():
    lut = {
        'epoch':0,
        'train_iter':0,
        'valid_iter':0,
        'train_losses':[],
        'valid_losses':[],
    }

    def get_loss_df(self):
        train_loss_df = pd.DataFrame(self.lut['train_losses'],columns="loss")
        valid_loss_df = pd.DataFrame(self.lut['valid_losses'],columns="loss")

        def _cleanup(df):
            f = pd.DataFrame(df.loss.to_list(),index= df.index)
            f.columns = [f"loss_{idx}" for idx,col in enumerate(f.columns)]
            x = pd.concat([df,f],axis=1)
            x=x.drop(columns=['loss'])
            return x

        return _cleanup(train_loss_df),_cleanup(valid_loss_df)

# Cell
class _logger():
    folder = None
    log_file = None

    def __init__(self, exp_folder=None):
        if exp_folder is not None:
            self.folder = exp_folder
        else:
            self.folder = Path("debug")

        self.log_file = self.folder/"log.txt"

        self.folder.mkdir(parents=True,exist_ok=True)

        self.__call__(">"*40)
        self.__call__(datetime.now().strftime("%d/%m/%Y %H:%M:%S"))

    def __call__(self, msg):
        if self.log_file:
            with self.log_file.open("a") as f:
                f.write(msg)
                f.write("\n")
        sys.stdout.write(msg+"\n")
        sys.stdout.flush()

# Cell

def _post_process_result(result):
    f = lambda x: np.format_float_positional(x,precision=DISPLAY_DECIMALS)
    vf = np.vectorize(f)
    return vf(result)

# Cell
def _eval_fn_on_predictions(eval_fn, predictions, ground_truth):
    # get the functions's name
    try:
        name = eval_fn.__name__
    except:
        name = eval_fn.__class__.__name__

    try:
        result = eval_fn(predictions, ground_truth)
        result = _post_process_result(result)
    except Exception as e:
        result = str(e)

    return name,result

# Cell
def _eval_fns_on_ds(learner, ds, fns, info=''):
    results = {}
    predictions, ground_truth, loss_values = learner.predict(ds,info)
    for fn in fns:
        fn_name, result = _eval_fn_on_predictions(fn, predictions, ground_truth)
        results[fn_name] = result

    loss_agg = np.asarray(loss_values).mean(axis=0)
    results['loss'] = _post_process_result(loss_agg)
    return results

# Cell
class _base_learner():
    eval_sets = defaultdict(list)
    def __init__(self, device, exp_folder=None, eval_sets:dict=None):

        self.device = _set_device(device)
        self.recorder = _recorder()
        self.logger = _logger()

        self.eval_sets['valid'] = [] # do validation always.

        for set_name in eval_sets:
            self.eval_sets[set_name].extend(force_list(eval_sets[set_name]))

    def on_backward_begin(self,loss):
        if isinstance(loss,(list,tuple)):
            return loss[0]
        else:
            return loss

    def on_backward_end(self):
        return

    def on_batch_begin(self, data_batch, phase='train'):
        # do somthing . with a batch of data
        # print(xb.mean(),xb.std(),xb.shape)
        xb,yb = data_batch['x'] , data_batch['y']
        return xb,yb

    def on_batch_end(self,xb,yb,pb,loss,is_train=True):
        # log losses
        if is_train:
            lst = self.recorder.lut['train_losses']
            epoch_num = self.recorder.lut['epoch']
            iter_num  = epoch_num*len(self.data['train'])+self.recorder.lut['train_iter']
        else:
            lst = self.recorder.lut['valid_losses']
            epoch_num = self.recorder.lut['epoch']
            iter_num  = epoch_num*len(self.data['valid'])+self.recorder.lut['valid_iter']
        if isinstance(loss,(list,tuple)):
            loss = [l.tolist() for l in loss]
        else:
            loss = [loss.tolist(),]

        def get_lr():
            for param_group in self.optimizer.param_groups:
                return param_group['lr']

        lst.append({
            'epoch_num':epoch_num,
            'iter_num':iter_num,
            'loss':loss,
            'lr':get_lr(),
        })

        # increment counters
        if is_train==True:
            self.recorder.lut['train_iter']+=1
        else:
            self.recorder.lut['valid_iter']+=1

    def on_epoch_end(self, ep_num):
        epoch_num= self.recorder.lut['epoch']

        train_losses = filter(lambda itm: itm['epoch_num'] == epoch_num, self.recorder.lut['train_losses'])
        # valid_losses = filter(lambda itm: itm['epoch_num'] == epoch_num, self.recorder.lut['valid_losses'])

        def _redux(loss_list_struct):
            loss_list_struct = [itm['loss'] for itm in loss_list_struct]
            loss_list_struct = np.asarray(loss_list_struct)
            return loss_list_struct

        average_train_loss = _redux(train_losses).mean(axis=0)

        self.recorder.lut['train_losses'].append({
            'epoch_num':epoch_num,
            'iter_num':-1,
            'loss':average_train_loss,
        })


        self.recorder.lut['epoch']+=1
        self.recorder.lut['train_iter']=0
        self.recorder.lut['valid_iter']=0

        eval_results = self.eval_metrics()

        eval_results['train']['loss'] = [_post_process_result(average_train_loss),]

        t = []
        for k,d in eval_results.items():
            for kk,v in d.items():
                t.append((kk,k))
        t = sorted(t, key=lambda tup: (tup[0],tup[1]))
        cols = pd.MultiIndex.from_tuples(t)
        df = pd.DataFrame(columns = cols)
        for k,d in eval_results.items():
            for kk,v in d.items():
                df[(kk,k)] = [v,]
        df.index = [epoch_num+1]
        df = df.rename_axis(["","EPOCH"], axis="columns")

        pd.set_option('max_colwidth', 500)
        s = df.to_string(na_rep='').split("\n")
        if ep_num==0:
            self.logger("\n".join(s))
        else: self.logger("\n".join(s[2:]))
        return

    def eval_metrics(self):
        """
           Evaluate model on set of data
        """
        eval_results = defaultdict(dict)

        for eval_set_name in self.eval_sets:
            eval_results[eval_set_name] = {}
            if eval_set_name in self.data:
                eval_results[eval_set_name] = _eval_fns_on_ds(
                    self,
                    self.data[eval_set_name],
                    self.eval_sets[eval_set_name],
                    info = eval_set_name
                )
            else:
                eval_results[eval_set_name]['error'] = "na in ds"
        return eval_results

# Cell
class Learner(_base_learner):
    def __init__(self, model, data, loss_func, optimizer,scheduler=None, *args, **kwargs):
        self.model,self.data,self.loss_func,self.optimizer,self.scheduler = model,data,loss_func,optimizer,scheduler
        super().__init__(*args, **kwargs)

    def fit(self, num_epochs=5):
        model, optimizer = self.model, self.optimizer

        for epoch in range(num_epochs):
            # train loop
            _dataset_forward_pass(
                ProgressBar(self.data['train'], status = "{}/{}".format(epoch+1,num_epochs)),
                self.model,
                self.loss_func,
                True, # is_train
                self.on_batch_begin,
                self.on_batch_end,
                self.on_backward_begin,
                self.on_backward_end,
                self.optimizer,
                self.device
            )


            # clean up
            self.on_epoch_end(epoch)

    def predict(self, dl, info=''):
        # TODO: make better !!
        P,Y,L = [],[],[]
        def prediction_recorder_fn(xb,yb,pb,loss,is_train):
            if isinstance(loss,(list,tuple)):
                loss = [l.tolist() for l in loss]
            else:
                loss = [loss.tolist(),]
            L.append(loss)
            P.append(pb)
            Y.append(yb)

        def _post(arr):
            if isinstance(arr[0],(list,tuple)):
                arr = list(zip(*arr))
                arr = [_post2(a) for a in arr]
                return arr
            if isinstance(arr[0],(torch.Tensor)):
                return np.concatenate([a.cpu().numpy() for a in arr])

        _dataset_forward_pass(
            ProgressBar(dl,info),
            self.model,
            self.loss_func,
            False, # is_train
            self.on_batch_begin,
            prediction_recorder_fn,
            None,
            None,
            None,
            self.device
        )


        Y = _post(Y)
        P = _post(P)


        return P,Y,L

# Cell

# Metrics
def accuracy(predictions, grnd_truth):
    p = predictions
    g = grnd_truth
    p = p.argmax(axis=1)
    return (p==g).mean()