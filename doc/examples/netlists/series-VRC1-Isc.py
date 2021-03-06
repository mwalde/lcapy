from lcapy import *
from numpy import logspace
from matplotlib.pyplot import savefig, show

N = Vstep(10) + R(10) + C(1e-4, 0)

vf = logspace(0, 5, 400)
N.Isc.frequency_response().plot(vf, log_scale=True)

show()

savefig('series-VRC1-Isc.png')
