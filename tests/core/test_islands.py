import numpy as np

from nirik.core.islands import grow, islands


def sheet():
    a = np.zeros((100, 200))
    a[10:40, 10:60] = 1      # row 1, left
    a[12:38, 120:180] = 1    # row 1, right
    a[60:90, 30:70] = 1      # row 2
    a[70:72, 150:152] = 1    # speck: too small
    return a


def test_islands_in_reading_order_without_specks():
    boxes = islands(sheet(), step=1, min_area=16)
    assert boxes == [(10, 10, 60, 40), (120, 12, 180, 38), (30, 60, 70, 90)]


def test_downsampled_boxes_cover_the_art():
    for (x0, y0, x1, y1), (fx0, fy0, fx1, fy1) in zip(islands(sheet(), step=4, min_area=16),
                                                       islands(sheet(), step=1, min_area=16)):
        assert x0 <= fx0 and y0 <= fy0 and x1 >= fx1 and y1 >= fy1


def test_glow_below_threshold_does_not_merge_pieces():
    a = sheet()
    a[20:30, 60:120] = 0.2   # faint glow bridging the two top pieces
    assert len(islands(a, step=1, min_area=16)) == 3


def test_grow_clamps_to_image():
    assert grow((5, 5, 95, 45), 10, 100, 50) == (0, 0, 100, 50)
