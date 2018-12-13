"""
Implement query strategies for multi-label setting.

There are 2 categories of methods.
1. Query instance-label pairs: QUIRE (TPAMI’14), AUDI (ICDM’13), Random

2. Query all labels of an instance: MMC (KDD’09), Adaptive (IJCAI’13), Random
"""

# Authors: Ying-Peng Tang
# License: BSD 3 clause

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import math
import numpy as np

from sklearn.metrics.pairwise import linear_kernel, polynomial_kernel, rbf_kernel

from .base import BaseMultiLabelQuery
from ..utils.misc import nsmallestarg, randperm


class _LabelRankingModel:
    """Label ranking model is a classification model in multi-label setting.
    It combines label ranking with threshold learning, and use SGD to optimize.

    It accept 3 types of labels:
    1 : relevant
    0.5 : less relevant
    -1 : irrelevant

    The labels in algorithms mean:
    2 : dummy
    0 : unknown (not use this label when updating)

    This class is mainly used for AURO and AUDI method for multi label querying.

    Parameters
    ----------
    X: 2D array
        Feature matrix of the initial data for training.
        Shape is n*d, one row for an instance with d features.

    y: 2D array
        Label matrix of the initial data for training.
        Shape is n*n_classes, one row for an instance, -1 means irrelevant,
        a positive value means relevant, the larger, the more relevant.
    """

    def __init__(self, init_X, init_y):
        assert len(init_X) == len(init_y)
        assert len(np.shape(init_y)) == 2
        self._init_X = np.asarray(init_X)
        self._init_y = np.asarray(init_y)

        if len(np.nonzero(self._init_y == 2.0)[0]) == 0:
            self._init_y = np.hstack((self._init_y, 2 * np.ones((self._init_y.shape[0], 1))))
        # B, V, AB, AV, Anum, trounds, costs, norm_up, step_size0, num_sub, lmbda, avg_begin, avg_size, n_repeat, \
        # max_query = self.init_model_train(self._init_X, self._init_y)

    def get_BV(self, AB, AV, Anum):
        return (AV / Anum).T.dot(AB / Anum)

    def init_model_train(self, init_data=None, init_targets=None):
        if init_data is None:
            init_data = self._init_X
        if init_targets is None:
            init_targets = self._init_y

        tar_sh = np.shape(init_targets)
        d = np.shape(init_data)[1]
        n_class = tar_sh[1]
        n_repeat = 10
        max_query = math.floor(tar_sh[0] * (tar_sh[1] - 1) / 2)
        D = 200
        num_sub = 5
        norm_up = np.inf
        lmbda = 0
        step_size0 = 0.05
        avg_begin = 10
        avg_size = 5

        costs = 1. / np.arange(start=1, stop=n_class * 5 + 1)
        for k in np.arange(start=1, stop=n_class * 5):
            costs[k] = costs[k - 1] + costs[k]

        V = np.random.normal(0, 1 / np.sqrt(d), (D, d))
        B = np.random.normal(0, 1 / np.sqrt(d), (D, n_class * num_sub))

        for k in range(d):
            tmp1 = V[:, k]
            if np.all(tmp1 > norm_up):
                V[:, k] = tmp1 * norm_up / np.linalg.norm(tmp1)
        for k in range(n_class * num_sub):
            tmp1 = B[:, k]
            if np.all(tmp1 > norm_up):
                B[:, k] = tmp1 * norm_up / np.linalg.norm(tmp1)

        AB = 0
        AV = 0
        Anum = 0
        trounds = 0

        for rr in range(n_repeat):
            B, V, AB, AV, Anum, trounds = self.fit(init_data, init_targets, B, V, np.zeros((1, tar_sh[0])),
                                                   np.zeros((1, tar_sh[0])), costs, norm_up, step_size0, num_sub,
                                                   AB, AV, Anum, trounds, lmbda, avg_begin, avg_size)

        return B, V, AB, AV, Anum, trounds, costs, norm_up, step_size0, num_sub, lmbda, avg_begin, avg_size, n_repeat, max_query

    def fit(self, data, targets, B, V, idxPs, idxNs, costs, norm_up, step_size0, num_sub, AB, AV, Anum, trounds, lmbda,
            average_begin, average_size):
        """targets: 0 unlabeled, 1 positive, -1 negative, 2 dummy, 0.5 less positive"""
        targets = np.asarray(targets)
        # print(np.nonzero(targets == 2.0))
        if len(np.nonzero(targets == 2.0)[0]) == 0:
            targets = np.hstack((targets, 2 * np.ones((targets.shape[0], 1))))
        data = np.asarray(data)
        B = np.asarray(B)
        V = np.asarray(V)

        n, n_class = np.shape(targets)
        tmpnums = np.sum(targets >= 1, axis=1)
        train_pairs = np.zeros((sum(tmpnums), 1))
        tmpidx = 0

        for i in range(n):
            train_pairs[tmpidx + 1: tmpidx + tmpnums[i]] = i
            tmpidx = tmpidx + tmpnums[i]

        targets = targets.T
        # tp = np.nonzero(targets.flatten() >= 1)
        # print(tp[0])
        # print(len(tp[0]))
        train_pairs = np.hstack(
            (train_pairs, np.reshape([nz % n_class for nz in np.nonzero(targets.flatten() >= 1)[0]], newshape=(-1, 1))))
        train_pairs[np.nonzero(train_pairs[:, 1] == 0)[0], 1] = n_class
        targets = targets.T

        n = np.shape(train_pairs)[0]
        random_idx = randperm(n-1)

        for i in range(n):
            idx_ins = int(train_pairs[random_idx[i], 0])
            xins = data[int(idx_ins), :].T
            idx_class = int(train_pairs[random_idx[i], 1])
            if idx_class == n_class:
                idx_irr = np.nonzero(targets[idx_ins, :] == -1)[0]
            elif idx_class == idxPs[0, idx_ins]:
                idx_irr = np.hstack((np.nonzero(targets[idx_ins, :] == -1)[0], idxNs[idx_ins], n_class-1))
            else:
                idx_irr = np.hstack((np.nonzero(targets[idx_ins, :] == -1)[0], n_class-1))
            n_irr = len(idx_irr)

            By = B[:, (idx_class - 1) * num_sub + 1: idx_class * num_sub]
            Vins = V.dot(xins)
            fy = np.max(By.T.dot(Vins), axis=0)
            idx_max_class = np.argmax(By.T.dot(Vins), axis=0)
            By = By[:, idx_max_class]
            fyn = np.NINF
            for j in range(n_irr):
                idx_pick = idx_irr[randperm(n_irr-1, 1)[0]]
                Byn = B[:, idx_pick * num_sub + 1: (idx_pick+1) * num_sub]
                # [fyn, idx_max_pick] = max(Byn.T.dot(Vins),[],1)
                # if Byn == []:
                #     print(0)
                fyn = np.max(Byn.T.dot(Vins), axis=0)
                idx_max_pick = np.argmax(Byn.T.dot(Vins), axis=0)

                if fyn > fy - 1:
                    break

            if fyn > fy - 1:
                step_size = step_size0 / (1 + lmbda * trounds * step_size0)
                trounds = trounds + 1
                Byn = B[:, idx_pick * num_sub + idx_max_pick]
                loss = costs[math.floor(n_irr / (j+1))]
                tmp1 = By + step_size * loss * Vins
                tmp3 = np.linalg.norm(tmp1)
                if tmp3 > norm_up:
                    tmp1 = tmp1 * norm_up / tmp3
                tmp2 = Byn - step_size * loss * Vins
                tmp3 = np.linalg.norm(tmp2)
                if tmp3 > norm_up:
                    tmp2 = tmp2 * norm_up / tmp3
                V -= step_size * loss * (
                    B[:, [idx_pick * num_sub + idx_max_pick, (idx_class - 1) * num_sub + idx_max_class]].dot(
                        np.vstack((xins, -xins))))
                # matrix norm, but the axis is not sure
                norms = np.linalg.norm(V, axis=0)
                idx_down = np.nonzero(norms > norm_up)[0]
                B[:, (idx_class - 1) * num_sub + idx_max_class] = tmp1
                B[:, idx_pick * num_sub + idx_max_pick] = tmp2
                if idx_down:
                    norms[norms <= norm_up] = []
                    for k in range(len(idx_down)):
                        V[:, idx_down[k]] = V[:, idx_down[k]] * norm_up / norms[k]
            if trounds > average_begin and i % average_size == 0:
                AB = AB + B
                AV = AV + V
                Anum = Anum + 1

        return B, V, AB, AV, Anum, trounds

    def predict(self, BV, data, num_sub):
        BV = np.asarray(BV)
        data = np.asarray(data)

        fs = data.dot(BV)
        n = data.shape[0]
        n_class = int(fs.shape[1] / num_sub)
        pres = np.ones((n, n_class)) * np.NINF
        for j in range(num_sub):
            f = fs[:, j: fs.shape[1]: num_sub]
            assert(np.all(f.shape == pres.shape))
            pres = np.fmax(pres, f)
        labels = -np.ones((n, n_class - 1))
        for line in range(n_class-1):
            gt = np.nonzero(pres[:, line] > pres[:, n_class-1])[0]
            labels[gt, line] = 1
        return pres, labels


class QueryMultiLabelQUIRE(BaseMultiLabelQuery):
    """QUIRE will select an instance-label pair based on the
    informativeness and representativeness for multi-label setting.

    This method will train a multi label classification model by combining
    label ranking with threshold learning and use it to evaluate the unlabeled data.
    Thus it is no need to pass any model.

    Parameters
    ----------
    X: 2D array
        Feature matrix of the whole dataset. It is a reference which will not use additional memory.

    y: array-like
        Label matrix of the whole dataset. It is a reference which will not use additional memory.

    lambda: float, optional (default=1.0)
        A regularization parameter used in the regularization learning
        framework.

    kernel : {'linear', 'poly', 'rbf', callable}, optional (default='rbf')
        Specifies the kernel type to be used in the algorithm.
        It must be one of 'linear', 'poly', 'rbf', or a callable.
        If a callable is given it is used to pre-compute the kernel matrix
        from data matrices; that matrix should be an array of shape
        ``(n_samples, n_samples)``.

    degree : int, optional (default=3)
        Degree of the polynomial kernel function ('poly').
        Ignored by all other kernels.

    gamma : float, optional (default=1.)
        Kernel coefficient for 'rbf', 'poly'.

    coef0 : float, optional (default=1.)
        Independent term in kernel function.
        It is only significant in 'poly'.

    References
    ----------
    [1] Huang, S.; Jin, R.; and Zhou, Z. 2014. Active learning by
        querying informative and representative examples. IEEE
        Transactions on Pattern Analysis and Machine Intelligence
        36(10):1936–1949
    """

    def __init__(self, X, y, **kwargs):
        # K: kernel matrix
        super(QueryMultiLabelQUIRE, self).__init__(X, y)
        self.lmbda = kwargs.pop('lambda', 1.)
        self.kernel = kwargs.pop('kernel', 'rbf')
        if self.kernel == 'rbf':
            self.K = rbf_kernel(X=X, Y=X, gamma=kwargs.pop('gamma', 1.))
        elif self.kernel == 'poly':
            self.K = polynomial_kernel(X=X,
                                       Y=X,
                                       coef0=kwargs.pop('coef0', 1),
                                       degree=kwargs.pop('degree', 3),
                                       gamma=kwargs.pop('gamma', 1.))
        elif self.kernel == 'linear':
            self.K = linear_kernel(X=X, Y=X)
        elif hasattr(self.kernel, '__call__'):
            self.K = self.kernel(X=np.array(X), Y=np.array(X))
        else:
            raise NotImplementedError

        if not isinstance(self.K, np.ndarray):
            raise TypeError('K should be an ndarray')
        if self.K.shape != (len(X), len(X)):
            raise ValueError(
                'kernel should have size (%d, %d)' % (len(X), len(X)))
        self._nsamples, self._nclass = self.y.shape
        self.L = np.linalg.inv(self.K + self.lmbda * np.eye(len(X)))

    def select(self, label_index, unlabel_index, **kwargs):
        if len(unlabel_index) <= 1:
            return unlabel_index
        unlabel_index = list(self._check_multi_label_ind(unlabel_index))
        label_index = list(self._check_multi_label_ind(label_index))

        nU = len(unlabel_index)
        # Only use the 2nd element
        Uidx = [uind[1] for uind in unlabel_index]
        Sidx = [lind[1] for lind in label_index]
        Ys = [self.y[mlab_ind] for mlab_ind in unlabel_index]
        Luu = self.L[np.ix_(Uidx, Uidx)]
        Lsu = self.L[np.ix_(Sidx, Uidx)]
        LL = np.linalg.inv(Luu)
        # calculate the evaluation value for each pair in U
        vals = np.zeros(nU, 1)
        YsLsu = np.dot(Ys, Lsu)
        for i in range(nU):
            tmpidx = list(range(nU))
            tmpidx.remove(i)
            Lqq = Luu[i, i]
            Lqr = Luu[i, tmpidx]
            tmp0 = Lqq  # +Ys'*Lss*Ys;

            b = -(LL[i, tmpidx])
            invLrr = LL[np.ix_(tmpidx, tmpidx)] - b.T.dot(b) / LL[i, i]
            vt1 = YsLsu[:, tmpidx]
            vt2 = 2 * YsLsu[:, i]
            tmp1 = vt1 + Lqr
            tmp1 = vt2 - tmp1.dot(invLrr).dot(tmp1.T)
            tmp2 = vt1 - Lqr
            tmp2 = -vt2 - tmp2.dot(invLrr).dot(tmp2.T)
            vals[i] = np.max((tmp0 + tmp1), (tmp0 + tmp2))

        idx_selected = nsmallestarg(vals, 1)[0]
        return unlabel_index[idx_selected]


class QueryMultiLabelAUDI(BaseMultiLabelQuery):
    """AUDI select an instance-label pair based on Uncertainty and Diversity.

    This method will train a multilabel classification model by combining
    label ranking with threshold learning and use it to evaluate the unlabeled data.
    Thus it is no need to pass any model.

    Parameters
    ----------
    X: 2D array
        Feature matrix of the whole dataset. It is a reference which will not use additional memory.

    y: array-like
        Label matrix of the whole dataset. It is a reference which will not use additional memory.
    """
