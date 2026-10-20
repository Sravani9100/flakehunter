import threading

from counter import HitCounter


def test_concurrent_increments_are_counted():
    counter = HitCounter()

    def hit_many():
        for _ in range(50):
            counter.increment()

    threads = [threading.Thread(target=hit_many) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert counter.value == 200
