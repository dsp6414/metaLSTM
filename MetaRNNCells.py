# encoding:utf-8
'''
@Author: catnlp
@Email: wk_nlp@163.com
@Time: 2018/4/25 21:19
'''
import RNNCells
from utils import clip_grad
import math

import torch
from torch.nn import Module, Parameter
import torch.nn.functional as F

class MetaRNNCellBase(Module):
    def __repr__(selfs):
        s = '{name}({input_size}, {hidden_size}, {hyper_hidden_size}, {hyper_embedding_size}'
        if 'bias' in self.__dict__ and self.bias is not True:
            s += ', bias={bias}'
        if 'bias_hyper' in self.__dict__ and self.bias is not True:
            s += ', bias_hyper={bias_hyper}'
        if 'nonlinearity' in self.__dict__ and self.nonlinearity != 'tanh':
            s += ', nonlinearity={nonlinearity}'
        s += ')'
        return s.format(name=self.__class__.__name__, **self.__dict__)

class MetaRNNCell(MetaRNNCellBase):
    def __init__(self, input_size, hidden_size, hyper_hidden_size, hyper_embedding_size, bias=True, bias_hyper=True, grad_clip=None):
        super(MetaRNNCell, self).__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.hyper_hidden_size = hyper_hidden_size
        self.hyper_embedding_size = hyper_embedding_size
        self.grad_clip = grad_clip

        self.weight_iH = Parameter(torch.Tensor(hidden_size, input_size))
        self.weight_HH = Parameter(torch.Tensor(hidden_size, hidden_size))

        self.weight_ih = Parameter(torch.Tensor(hyper_hidden_size, input_size))
        self.weight_hh = Parameter(torch.Tensor(hyper_hidden_size, hyper_hidden_size))
        self.weight_Hh = Parameter(torch.Tensor(hyper_hidden_size, hidden_size))

        self.weight_hz = Parameter(torch.Tensor(hyper_embedding_size, hyper_hidden_size))
        self.weight_dziH = Parameter(torch.Tensor(hidden_size, hyper_embedding_size))
        self.weight_dzHH = Parameter(torch.Tensor(hidden_size, hyper_embedding_size))
        self.weight_bzH = Parameter(torch.Tensor(hidden_size, hyper_embedding_size))
        if bias:
            self.bias = Parameter(torch.Tensor(hidden_size))
        else:
            self.register_parameter('bias', None)
        if bias_hyper:
            self.bias_hyper = Parameter(torch.Tensor(hyper_hidden_size))
        else:
            self.register_parameter('bias_hyper', None)

        self.reset_parameters()

    def reset_parameters(self):
        stdv = 1.0 / math.sqrt(self.hidden_size)
        for weight in self.parameters():
            weight.data.uniform_(-stdv, stdv)

    def forward(self, input, state):
        H = state[0]
        h = state[1]

        meta_output = F.linear(input, self.weight_ih) + F.linear(h, self.weight_hh) + F.linear(H, self.weight_Hh) + self.bias_hyper
        if self.grad_clip:
            meta_output = clip_grad(meta_output, -self.grad_clip, self.grad_clip)
        meta_output = F.relu(meta_output)

        z = F.linear(meta_output, self.weight_hz)

        output = F.linear(z, self.weight_dziH) * F.linear(input, self.weight_iH) + F.linear(z, self.weight_dzHH) * F.linear(H, self.weight_HH) + F.linear(z, self.weight_bzH)
        if self.grad_clip:
            output = clip_grad(output, -self.grad_clip, self.grad_clip)
        output = F.relu(output)
        return (output, meta_output)

class MetaLSTMCell(MetaRNNCellBase):
    def __init__(self, input_size, hidden_size, hyper_hidden_size, hyper_embedding_size, bias=True, bias_hyper=True, grad_clip=None):
        super(MetaLSTMCell, self).__init__()
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.hyper_hidden_size = hyper_hidden_size
        self.hyper_embedding_size = hyper_embedding_size
        self.grad_clip = grad_clip

        self.weight_iH = Parameter(torch.Tensor(4 * hidden_size, input_size))
        self.weight_HH = Parameter(torch.Tensor(4 * hidden_size, hidden_size))

        self.weight_ih = Parameter(torch.Tensor(4 * hyper_hidden_size, input_size + hidden_size))
        self.weight_hh = Parameter(torch.Tensor(4 * hyper_hidden_size, hyper_hidden_size))

        self.weight_hz = Parameter(torch.Tensor(hyper_embedding_size, hyper_hidden_size))
        self.weight_dziH = Parameter(torch.Tensor(4 * hidden_size, hyper_embedding_size))
        self.weight_dzHH = Parameter(torch.Tensor(4 * hidden_size, hyper_embedding_size))
        self.weight_bzH = Parameter(torch.Tensor(4 * hidden_size, hyper_embedding_size))
        if bias:
            self.bias = Parameter(torch.Tensor(4 * hidden_size))
        else:
            self.register_parameter('bias', None)
        if bias_hyper:
            self.bias_hyper = Parameter(torch.Tensor(4 * hyper_hidden_size))
        else:
            self.register_parameter('bias_hyper', None)

        self.reset_parameters()

    def reset_parameters(self):
        stdv = 1.0 / math.sqrt(self.hidden_size)
        for weight in self.parameters():
            weight.data.uniform_(-stdv, stdv)

    def forward(self, input, state):
        main_state = state[0]
        meta_state = state[1]
        main_h = main_state[0]
        main_c = main_state[1]
        meta_h = meta_state[0]
        meta_c = meta_state[1]

        meta_pre = F.linear(torch.cat((input, main_h), 1), self.weight_ih) + F.linear(meta_h, self.weight_hh) + self.bias_hyper
        if self.grad_clip:
            meta_pre = clip_grad(meta_pre, -self.grad_clip, self.grad_clip)

        meta_i = F.sigmoid(meta_pre[:, : self.hyper_hidden_size])
        meta_f = F.sigmoid(meta_pre[:, self.hyper_hidden_size: self.hyper_hidden_size * 2])
        meta_g = F.tanh(meta_pre[:, self.hyper_hidden_size * 2: self.hyper_hidden_size * 3])
        meta_o = F.sigmoid(meta_pre[:, self.hyper_hidden_size * 3: ])
        meta_c = meta_f * meta_c + meta_i * meta_g
        meta_h = meta_o * F.tanh(meta_c)

        z = F.linear(meta_h, self.weight_hz)

        pre = F.linear(z, self.weight_dziH) * F.linear(input, self.weight_iH) + F.linear(z, self.weight_dzHH) * F.linear(main_h, self.weight_HH) + F.linear(z, self.weight_bzH)
        if self.grad_clip:
            pre = clip_grad(pre, -self.grad_clip, self.grad_clip)

        main_i = F.sigmoid(pre[:, : self.hidden_size])
        main_f = F.sigmoid(pre[:, self.hidden_size: self.hidden_size * 2])
        main_g = F.tanh(pre[:, self.hidden_size * 2: self.hidden_size * 3])
        main_o = F.sigmoid(pre[:, self.hidden_size * 3:])
        main_c = main_f * main_c + main_i * main_g
        main_h = main_o * F.tanh(main_c)
        return ((main_h, main_c), (meta_h, meta_c))