from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import gc
import random
import numpy as np
import os,sys,pickle,re
import math
import time
from math import pi as Pi
import scipy.special
import itertools
import warnings
from collections import defaultdict
from collections import Counter
warnings.simplefilter(action = "ignore", category = FutureWarning)

#
# GLOBALS
#	Any global variables of the code must be put here, and must be in all caps.
#	Global variables are almost never acceptable except in these few cases


# PARAMETERS
#  TODO: have some type of param file.
MAX_ATOMIC_NUMBER = 10
GRIDS = None
MBE_ORDER = 2
HAS_GRIDS=True

# Derived Quantities and useful things.
HAS_PYSCF = False
HAS_EMB = False
HAS_TF = False
N_CORES = 1
ele_roomT_H = {1:-0.497912, 6:-37.844411, 7:-54.581501, 8:-75.062219, 9:-99.716370}     # ref: https://figshare.com/articles/Atomref%3A_Reference_thermochemical_energies_of_H%2C_C%2C_N%2C_O%2C_F_atoms./1057643
ele_U = {1:-0.500273, 6:-37.846772, 7:-54.583861, 8:-75.064579, 9:-99.718730}   # ref: https://figshare.com/articles/Atomref%3A_Reference_thermochemical_energies_of_H%2C_C%2C_N%2C_O%2C_F_atoms./1057643
atoi = {'H':1,'He':2,'Li':3,'Be':4,'B':5,'C':6,'N':7,'O':8,'F':9,'Ne':10,'Na':11,'Mg':12,'Al':13,'Si':14,'P':15,'S':16,'Cl':17,'Ar':18,'K':19,'Ca':20,'Sc':21,'Ti':22,'Si':23,'V':24,'Cr':25,'Br':35, 'Cs':55, 'Pb':82}
atoc = {1: 40, 6: 100, 7: 150, 8: 200, 9:240}
atom_valance = {1:1, 8:2, 7:3, 6:4}
bond_length_thresh = {"HH": 1.5, "HC": 1.5, "HN": 1.5, "HO": 1.5, "CC": 1.7, "CN": 1.7, "CO": 1.7, "NN": 1.7, "NO": 1.7, "OO": 1.7 }
bond_index = {"HH": 1, "HC": 2, "HN": 3, "HO": 4, "CC": 5, "CN": 6, "CO": 7, "NN": 8, "NO": 9, "OO": 10}
dihed_pair = {1006:1, 1007:2, 1008:3, 6006:4, 6007:5, 6008:6,  7006:7, 7007:8, 7008:9, 8006:10, 8007:11, 8008:12}  # atomic_1*1000 + atomic_2 hacky way to do that
atomic_radius = {1:53.0, 2:31.0, 3:167.0, 4:112.0, 5:87.0, 6:67.0, 7:56.0, 8:48.0, 9:42.0, 10:38.0, 11:190.0, 12:145.0, 13:118.0, 14:111.0, 15:98.0, 16:88.0, 17:79.0, 18:71.0} # units in pm, ref: https://en.wikipedia.org/wiki/Atomic_radius
atomic_radius_2 = {1:25.0, 3:145.0, 4:105.0, 5:85.0, 6:70.0, 7:65.0, 8:60.0, 9:50.0, 11:180.0, 12:150.0, 13:125.0, 14:110.0, 15:100.0, 16:100.0, 17:100.0} # units in pm, ref: https://en.wikipedia.org/wiki/Atomic_radius
atomic_vdw_radius = {1:1.001, 2:1.012, 3:0.825, 4:1.408, 5:1.485, 6:1.452, 7:1.397, 8:1.342, 9:1.287, 10:1.243} # ref: http://onlinelibrary.wiley.com/doi/10.1002/jcc.20495/epdf   unit in angstrom
C6_coff = {1:0.14, 2:0.08, 3:1.16, 4:1.61, 5:3.13, 6:1.75, 7:1.23, 8:0.70, 9:0.75, 10:0.63}  # ref: http://onlinelibrary.wiley.com/doi/10.1002/jcc.20495/epdf unit in Jnm^6/mol
S6 = {"PBE": 0.75, "BLYP":1.2, "B-P86":1.05, "TPSS":1.0, "B3LYP":1.05}  # s6 scaler of different DF of Grimmer C6 scheme
atomic_raidus_cho = {1:0.328, 6:0.754, 8:0.630} # roughly statisfy mp2 cc-pvtz equilibrium carbohydrate bonds.
KAYBEETEE = 0.000950048 # At 300K
BOHRPERA = 1.889725989
Qchem_RIMP2_Block = "$rem\n   jobtype   sp\n   method   rimp2\n   MAX_SCF_CYCLES  200\n   basis   cc-pvtz\n   aux_basis rimp2-cc-pvtz\n   symmetry   false\n   INCFOCK 0\n   thresh 12\n   SCF_CONVERGENCE 12\n$end\n"

#
# -- begin Environment set up.
#
print("--------------------------\n")
print("         /\\______________")
print("      __/  \\   \\_________")
print("    _/  \\   \\            ")
print("___/\_TensorMol_0.0______")
print("   \\_/\\______  __________")
print("     \\/      \\/          ")
print("      \\______/\\__________\n")
print("--------------------------")
print("By using this software you accept the terms of the GNU public license in ")
print("COPYING, and agree to attribute the use of this software in publications as: \n")
print("K.Yao, J. E. Herr, J. Parkhill. TensorMol0.0 (2016)")
print("Depending on Usage, please also acknowledge, TensorFlow, PySCF, or your training sets.")
print("--------------------------")
print("Searching for Installed Optional Packages...")
try:
	from pyscf import scf
	from pyscf import gto
	from pyscf import dft
	from pyscf import mp
	HAS_PYSCF = True
	print("Pyscf has been found")
except Exception as Ex:
	print("Pyscf is not installed -- no ab-initio sampling",Ex)
	pass

try:
	import MolEmb
	HAS_EMB = True
	print("MolEmb has been found")
except:
	print("MolEmb is not installed. Please cd C_API; sudo python setup.py install")
	pass

try:
	import tensorflow as tf
	tf.logging.set_verbosity(tf.logging.DEBUG)
	HAS_TF = True
	print("Tensorflow version "+tf.__version__+" has been found")
except:
	print("Tensorflow not Installed, very limited functionality")
	pass

try:
	import multiprocessing
	N_CORES=multiprocessing.cpu_count()
	print("Found "+str(N_CORES)+" CPUs to thread over... ")
except:
	print("Only a single CPU, :( did you lose a war?")
	pass

print("TensorMol ready...")

TOTAL_SENSORY_BASIS=None
SENSORY_BASIS=None
if (HAS_PYSCF and HAS_GRIDS):
	from TensorMol.Grids import *
	GRIDS = Grids()
#	GRIDS.Populate()
print("--------------------------")
#
# -- end Environment set up.
#

def complement(a,b):
	return [i for i in a if b.count(i)==0]

def scitodeci(sci):
	tmp=re.search(r'(\d+\.?\d+)\*\^(-?\d+)',sci)
	return float(tmp.group(1))*pow(10,float(tmp.group(2)))

def AtomicNumber(Symb):
	try:
		return atoi[Symb]
	except Exception as Ex:
		raise Exception("Unknown Atom")
	return 0

def AtomicSymbol(number):
	try:
		return atoi.keys()[atoi.values().index(number)]
	except Exception as Ex:
		raise Exception("Unknown Atom")
	return 0

def SignStep(S):
	if (S<0.5):
		return -1.0
	else:
		return 1.0

# Choose random samples near point...
def PointsNear(point,NPts,Dist):
	disps=Dist*0.2*np.abs(np.log(np.random.rand(NPts,3)))
	signs=signstep(np.random.random((NPts,3)))
	return (disps*signs)+point

def SamplingFunc_v2(S, maxdisp):    ## with sampling function f(x)=M/(x+1)^2+N; f(0)=maxdisp,f(maxdisp)=0; when maxdisp =5.0, 38 % lie in (0, 0.1)
	M = -((-1 - 2*maxdisp - maxdisp*maxdisp)/(2 + maxdisp))
	N = ((-1 - 2*maxdisp - maxdisp*maxdisp)/(2 + maxdisp)) + maxdisp
	return M/(S+1.0)**2 + N

def LtoS(l):
	s=""
	for i in l:
		s+=str(i)+" "
	return s

def ErfSoftCut(dist, width, x):
	return (1-scipy.special.erf(1.0/width*(x-dist)))/2.0

def CosSoftCut(dist, x):
	if x > dist:
		return 0
	else:
		return 0.5*(math.cos(math.pi*x/dist)+1.0)

	return

def nCr(n, r):
	f = math.factorial
	return int(f(n)/f(r)/f(n-r))

def Submit_Script_Lines(order=str(3), sub_order =str(1), index=str(1), mincase = str(0), maxcase = str(1000), name = "MBE", ncore = str(4), queue="long"):
	lines = "#!/bin/csh\n"+"# Submit a job for 8  processors\n"+"#$ -N "+name+"\n#$ -t "+mincase+"-"+maxcase+":1\n"+"#$ -pe smp "+ncore+"\n"+"#$ -r n\n"+"#$ -q "+queue+"\n\n\n"
	lines += "module load gcc/5.2.0\nsetenv  QC /afs/crc.nd.edu/group/parkhill/qchem85\nsetenv  QCAUX /afs/crc.nd.edu/group/parkhill/QCAUX_1022\nsetenv  QCPLATFORM LINUX_Ix86\n\n\n"
	lines += "/afs/crc.nd.edu/group/parkhill/qchem85/bin/qchem  -nt "+ncore+"   "+str(order)+"/"+"${SGE_TASK_ID}/"+sub_order+"/"+index+".in  "+str(order)+"/"+"${SGE_TASK_ID}/"+sub_order+"/"+index+".out\n\nrm MBE*.o*"
	return lines

def Binominal_Combination(indis=[0,1,2], group=3):
	if (group==1):
		index=list(itertools.permutations(indis))
		new_index =[]
		for i in range (0, len(index)):
			new_index.append(list(index[i]))
		return new_index
	else:
		index=list(itertools.permutations(indis))
		new_index=[]
		for sub_list in Binominal_Combination(indis, group-1):
			for sub_index in index:
				new_index.append(list(sub_list)+list(sub_index))
		return new_index

def NormMatrices(mat1, mat2):
	#Only faster due to subtraction of matrices being done in C_API, possibly remove
	assert mat1.shape == mat2.shape, "Shape of matrices must match to calculate the norm"
	return MolEmb.Norm_Matrices(mat1, mat2)

def String_To_Atoms(s=""):
	l = list(s)
	atom_l = []
	tmp = ""
	for i, c in enumerate(l):
		if  ord('A') <= ord(c) <= ord('Z'):
			tmp=c
		else:
			tmp += c
		if i==len(l)-1:
			atom_l.append(tmp)
		elif ord('A') <= ord(l[i+1]) <= ord('Z'):
			atom_l.append(tmp)
		else:
			continue
	return atom_l

def iter_product(args, repeat=1):
    # product('ABCD', 'xy') --> Ax Ay Bx By Cx Cy Dx Dy
    # product(range(2), repeat=3) --> 000 001 010 011 100 101 110 111
    pools = [tuple(pool) for pool in args] * repeat
    result = [[]]
    for pool in pools:
        result = [x+[y] for x in result for y in pool]
    for prod in result:
        yield list(prod)

def Subset(A, B): # check whether B is subset of A
	checked_index = []
	found = 0
	for value in B:
		for i in range (0, len(A)):
			if value==A[i] and i not in checked_index:
				checked_index.append(i)	
				found += 1
				break
	if found == len(B):
		return True
	else:
		return False 

def Setdiff(A, B): # return the element of A that not included in B
	diff = []
	checked_index = []
	for value in A:
		found = 0
		for i in range (0, len(B)):
			if value == B[i] and i not in checked_index:
				found = 1
				checked_index.append(i)
				break
		if found == 0:
			diff.append(value)
	return diff

def Pair_In_List(l, pairs): # check whether l contain pair
	for pair in pairs:
		if Subset(l, pair):
			return True
	return False

def Dihed_4Points(x1, x2, x3, x4): # dihedral angle constructed by x1 - x2 - x3 - x4
	b1 = x2 - x1
	b2 = x3 - x2
	b3 = x4 - x3
	c1 = np.cross(b1, b2)
	c1 = c1/np.linalg.norm(c1)
	c2 = np.cross(b2, b3)
        c2 = c2/np.linalg.norm(c2)
	b2 = b2/np.linalg.norm(b2)
	return math.atan2(np.dot(np.cross(c1, c2), b2), np.dot(c1, c2))	

signstep = np.vectorize(SignStep)
samplingfunc_v2 = np.vectorize(SamplingFunc_v2)
