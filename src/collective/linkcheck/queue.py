from ZODB.POSException import ConflictError
from zc.queue._queue import BucketQueue
from zc.queue import CompositeQueue


class CompositeQueue(CompositeQueue):
    def __init__(self, compositeSize=15, subfactory=BucketQueue):
        super(CompositeQueue, self).__init__(compositeSize, subfactory)
        self.size = 0

    def pull(self, index=0):
        item = super(CompositeQueue, self).pull(index)
        self.size -= 1
        return item

    def put(self, item):
        super(CompositeQueue, self).put(item)
        self.size += 1

    def __getitem__(self, index):
        """Optimize frequently accessed index."""

        if index == -1:
            queue = index
            while not len(self._data[queue]):
                queue -= 1
            return self._data[queue][-1]

        if isinstance(index, slice):
            start, stop, stride = index.indices(len(self))
            res = []
            stride_ct = 1
            for ix, v in enumerate(self):
                if ix >= stop:
                    break
                if ix < start:
                    continue
                stride_ct -= 1
                if stride_ct == 0:
                    res.append(v)
                    stride_ct = stride
            return res
        else:
            if index < 0:  # not efficient, but quick and easy
                len_self = len(self)
                rindex = index + len_self
                if rindex < 0:
                    raise IndexError(index)
            else:
                rindex = index
            for ix, v in enumerate(self):
                if ix == rindex:
                    return v
            raise IndexError(index)

    def __len__(self):
        return self.size

    def _p_resolveConflict(self, oldstate, committedstate, newstate):
        return resolveQueueConflict(oldstate, committedstate, newstate)


def resolveQueueConflict(oldstate, committedstate, newstate, bucket=False):
    # We only know how to merge _data and the size of the top-level queue.
    # If anything else is different, puke.
    if set(committedstate.keys()) != set(newstate.keys()):
        raise ConflictError  # can't resolve
    for key, val in newstate.items():
        if key not in ('_data', 'size')  and val != committedstate[key]:
            raise ConflictError  # can't resolve

    # basically, we are ok with anything--willing to merge--
    # unless committedstate and newstate have one or more of the
    # same deletions or additions in comparison to the oldstate.
    old = oldstate['_data']
    committed = committedstate['_data']
    new = newstate['_data']

    old_set = set(old)
    committed_set = set(committed)
    new_set = set(new)

    if bucket and bool(old_set) and (bool(committed_set) ^ bool(new_set)):
        # This is a bucket, part of a CompositePersistentQueue.  The old set
        # of this bucket had items, and one of the two transactions cleaned
        # it out.  There's a reasonable chance that this bucket will be
        # cleaned out by the parent in one of the two new transactions.
        # We can't know for sure, so we take the conservative route of
        # refusing to be resolvable.
        raise ConflictError

    committed_added = committed_set - old_set
    committed_removed = old_set - committed_set
    new_added = new_set - old_set
    new_removed = old_set - new_set

    if new_removed & committed_removed:
        # they both removed (claimed) the same one.  Puke.
        raise ConflictError  # can't resolve
    elif new_added & committed_added:
        # they both added the same one.  Puke.
        raise ConflictError  # can't resolve

    # Now we do the merge.  We'll merge into the committed state and
    # return it.
    mod_committed = []
    for v in committed:
        if v not in new_removed:
            mod_committed.append(v)
    if new_added:
        ordered_new_added = new[-len(new_added):]
        assert set(ordered_new_added) == new_added
        mod_committed.extend(ordered_new_added)
    # Set the new size on top level queues
    if not bucket:
        committed_size_diff = committedstate['size'] - oldstate['size']
        new_size_diff = newstate['size'] - oldstate['size']
        new_size = oldstate['size'] + committed_size_diff + new_size_diff
        committedstate['size'] = new_size
    committedstate['_data'] = tuple(mod_committed)
    return committedstate
