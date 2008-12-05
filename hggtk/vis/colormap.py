# Copyright (C) 2005 Dan Loda <danloda@gmail.com>

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
import sys

class AnnotateColorMap:

    really_old_color = "#0046FF"

    colors = {
        20.: "#FF0000",
        40.: "#FF3800",
        60.: "#FF7000",
        80.: "#FFA800",
        100.:"#FFE000",
        120.:"#E7FF00",
        140.:"#AFFF00",
        160.:"#77FF00",
        180.:"#3FFF00",
        200.:"#07FF00",
        220.:"#00FF31",
        240.:"#00FF69",
        260.:"#00FFA1",
        280.:"#00FFD9",
        300.:"#00EEFF",
        320.:"#00B6FF",
        340.:"#007EFF"
    }

    def __init__(self, span=340.):
        self.set_span(span)

    def set_span(self, span):
        self._span = span
        self._scale = span / max(self.colors.keys())

    def _days(self, ctx, now):
        return (now - ctx.date()[0]) / (24 * 60 * 60)

    def get_color(self, ctx, now):
        color = self.really_old_color
        days = self.colors.keys()
        days.sort()
        days_old = self._days(ctx, now)
        for day in days:
            if (days_old <= day * self._scale):
                color = self.colors[day]
                break

        return color

class AnnotateColorSaturation(AnnotateColorMap):
    def __init__(self, span=340.):
        AnnotateColorMap.__init__(self, span)
        self.current_angle = 0

    def hue(self, angle):
        return tuple([self.v(angle, r) for r in (0, 120, 240)])

    @staticmethod
    def ang(angle, rotation):
        angle += rotation
        angle = angle % 360
        if angle > 180:
            angle = 180 - (angle - 180)
        return abs(angle)

    def v(self, angle, rotation):
        ang = self.ang(angle, rotation)
        if ang < 60:
            return 1
        elif ang > 120:
            return 0
        else:
            return 1 - ((ang - 60) / 60)

    def saturate_v(self, saturation, hv):
        return int(255 - (saturation/3*(1-hv)))
    
    def committer_angle(self, committer):
        return float(abs(hash(committer))) / sys.maxint * 360.0

    def get_color(self, ctx, now):
        days = self._days(ctx, now)
        saturation = 255/((days/50) + 1)
        #saturation = 255/((days/self._scale) + 1)
        hue = self.hue(self.committer_angle(ctx.user()))
        color = tuple([self.saturate_v(saturation, h) for h in hue])
        return "#%x%x%x" % color
