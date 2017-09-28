from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from TensorMol.TFInstance import *
from TensorMol.TensorMolData import *
import numpy as np
import math,pickle
import time
import os.path
if (HAS_TF):
	import tensorflow as tf
import os
import sys

#
# These work Moleculewise the versions without the mol prefix work atomwise.
# but otherwise the behavior of these is the same as TFInstance etc.
#

class MolInstance(Instance):
	def __init__(self, TData_,  Name_=None):
		Instance.__init__(self, TData_, 0, Name_)
		if Name_:   # it already been Loaded in the instance.__init__
			return
		self.TData.LoadDataToScratch()
		self.learning_rate = 0.001
		#self.learning_rate = 0.0001 # for adam
		#self.learning_rate = 0.00001 # for adadelta
		#self.learning_rate = 0.000001 # 1st sgd
		#self.learning_rate = 0.0000001  #Pickle do not like to pickle  module, replace all the FLAGS with self.
		self.momentum = 0.9
		self.max_steps = 10000
		self.batch_size = 1000 # This is just the train batch size.
		self.name = "Mol_"+self.TData.name+"_"+self.TData.dig.name+"_"+str(self.TData.order)+"_"+self.NetType
		self.train_dir = './networks/'+self.name
		self.TData.PrintStatus()
		self.normalize= True
		self.inshape =  self.TData.dig.eshape  # use the flatted version
		self.outshape = self.TData.dig.lshape    # use the flatted version
		print ("inshape", self.inshape, "outshape", self.outshape)
		print ("std of the output", (self.TData.scratch_outputs.reshape(self.TData.scratch_outputs.shape[0])).std())
		return

	def inference(self, images, hidden1_units, hidden2_units, hidden3_units):
		"""Build the MNIST model up to where it may be used for inference.
		Args:
		images: Images placeholder, from inputs().
		hidden1_units: Size of the first hidden layer.
		hidden2_units: Size of the second hidden layer.
		Returns:
		softmax_linear: Output tensor with the computed logits.
		"""
		# Hidden 1
		with tf.name_scope('hidden1'):
			weights = self._variable_with_weight_decay(var_name='weights', var_shape=[self.inshape, hidden1_units], var_stddev= 1 / math.sqrt(float(self.inshape)), var_wd= 0.00)
			biases = tf.Variable(tf.zeros([hidden1_units]),
			name='biases')
			hidden1 = tf.nn.relu(tf.matmul(images, weights) + biases)
			tf.scalar_summary('min/' + weights.name, tf.reduce_min(weights))
			tf.histogram_summary(weights.name, weights)
		# Hidden 2
		with tf.name_scope('hidden2'):
			weights = self._variable_with_weight_decay(var_name='weights', var_shape=[hidden1_units, hidden2_units], var_stddev= 1 / math.sqrt(float(hidden1_units)), var_wd= 0.00)
			biases = tf.Variable(tf.zeros([hidden2_units]),
			name='biases')
			hidden2 = tf.nn.relu(tf.matmul(hidden1, weights) + biases)
		# Linear
		with tf.name_scope('regression_linear'):
				weights = self._variable_with_weight_decay(var_name='weights', var_shape=[hidden2_units, self.outshape], var_stddev= 1 / math.sqrt(float(hidden2_units)), var_wd= 0.00)
				biases = tf.Variable(tf.zeros([self.outshape]),
				name='biases')
				output = tf.matmul(hidden2, weights) + biases
		return output

	def train(self, mxsteps, continue_training= False):
		self.train_prepare(continue_training)
		test_freq = 1000
		mini_test_loss = float('inf') # some big numbers
		for step in  range (0, mxsteps):
			self.train_step(step)
			if step%test_freq==0 and step!=0 :
				test_loss, feed_dict = self.test(step)
				if test_loss < mini_test_loss:
					mini_test_loss = test_loss
					if (step > 1000):
						self.save_chk(step, feed_dict)
		self.SaveAndClose()
		return

	def train_step(self,step):
		""" I don't think the base class should be
			train-able. Remove? JAP """
		Ncase_train = self.TData.NTrain
		start_time = time.time()
		train_loss =  0.0
		total_correct = 0
		for ministep in range (0, int(Ncase_train/self.batch_size)):
			batch_data=self.TData.GetTrainBatch( self.batch_size) #advances the case pointer in TData...
			feed_dict = self.fill_feed_dict(batch_data, self.embeds_placeholder, self.labels_placeholder)
			_, total_loss_value, loss_value, prob_value, correct_num  = self.sess.run([self.train_op, self.total_loss, self.loss, self.prob, self.correct], feed_dict=feed_dict)
			train_loss = train_loss + loss_value
			total_correct = total_correct + correct_num
		duration = time.time() - start_time
		self.print_training(step, train_loss, total_correct, Ncase_train, duration)
		return

class MolInstance_fc_classify(MolInstance):
	def __init__(self, TData_,  Name_=None):
		self.NetType = "fc_classify"
		MolInstance.__init__(self, TData_,  Name_)
		self.name = "Mol_"+self.TData.name+"_"+self.TData.dig.name+"_"+str(self.TData.order)+"_"+self.NetType
		self.train_dir = './networks/'+self.name
		self.hidden1 = 200
		self.hidden2 = 200
		self.hidden3 = 200
		self.prob = None
#		self.inshape = self.TData.scratch_inputs.shape[1]
		self.correct = None
		self.summary_op =None
		self.summary_writer=None

	def evaluation(self, output, labels):
		# For a classifier model, we can use the in_top_k Op.
		# It returns a bool tensor with shape [batch_size] that is true for
		# the examples where the label is in the top k (here k=1)
		# of all logits for that example.
		labels = tf.to_int64(labels)
		correct = tf.nn.in_top_k(output, labels, 1)
		# Return the number of true entries.
		return tf.reduce_sum(tf.cast(correct, tf.int32))

	def evaluate(self, eval_input):
		# Check sanity of input
		MolInstance.evaluate(self, eval_input)
		eval_input_ = eval_input
		if (self.PreparedFor>eval_input.shape[0]):
			eval_input_ =np.copy(eval_input)
			eval_input_.resize((self.PreparedFor,eval_input.shape[1]))
			# pad with zeros
		eval_labels = np.zeros(self.PreparedFor)  # dummy labels
		batch_data = [eval_input_, eval_labels]
		#images_placeholder, labels_placeholder = self.placeholder_inputs(Ncase) Made by Prepare()
		feed_dict = self.fill_feed_dict(batch_data,self.embeds_placeholder,self.labels_placeholder)
		tmp = (np.array(self.sess.run([self.prob], feed_dict=feed_dict))[0,:eval_input.shape[0],1])
		if (not np.all(np.isfinite(tmp))):
			print("TFsession returned garbage")
			print("TFInputs",eval_input) #If it's still a problem here use tf.Print version of the graph.
		if (self.PreparedFor>eval_input.shape[0]):
			return tmp[:eval_input.shape[0]]
		return tmp

	def Prepare(self, eval_input, Ncase=125000):
		self.Clean()
		print("Preparing a ",self.NetType,"MolInstance")
		self.prob = None
		self.correct = None
		# Always prepare for at least 125,000 cases which is a 50x50x50 grid.
		eval_labels = np.zeros(Ncase)  # dummy labels
		with tf.Graph().as_default(), tf.device('/job:localhost/replica:0/task:0/gpu:1'):
			self.embeds_placeholder, self.labels_placeholder = self.placeholder_inputs(Ncase)
			self.output = self.inference(self.embeds_placeholder, self.hidden1, self.hidden2, self.hidden3)
			self.correct = self.evaluation(self.output, self.labels_placeholder)
			self.prob = self.justpreds(self.output)
			self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True))
			self.saver = tf.train.Saver()
			self.saver.restore(self.sess, self.chk_file)
		self.PreparedFor = Ncase
		return

	def SaveAndClose(self):
		self.prob = None
		self.correct = None
		self.summary_op =None
		self.summary_writer=None
		MolInstance.SaveAndClose(self)
		return

	def placeholder_inputs(self, batch_size):
		"""Generate placeholder variables to represent the input tensors.
		These placeholders are used as inputs by the rest of the model building
		code and will be fed from the downloaded data in the .run() loop, below.
		Args:
		batch_size: The batch size will be baked into both placeholders.
		Returns:
		images_placeholder: Images placeholder.
		labels_placeholder: Labels placeholder.
		"""
		# Note that the shapes of the placeholders match the shapes of the full
		# image and label tensors, except the first dimension is now batch_size
		# rather than the full size of the train or test data sets.
		inputs_pl = tf.placeholder(tf.float32, shape=(batch_size,self.inshape)) # JAP : Careful about the shapes... should be flat for now.
		outputs_pl = tf.placeholder(tf.float32, shape=(batch_size))
		return inputs_pl, outputs_pl

	def justpreds(self, output):
		"""Calculates the loss from the logits and the labels.
		Args:
		logits: Logits tensor, float - [batch_size, NUM_CLASSES].
		labels: Labels tensor, int32 - [batch_size].
		Returns:
		loss: Loss tensor of type float.
		"""
		prob = tf.nn.softmax(output)
		return prob

	def loss_op(self, output, labels):
		"""Calculates the loss from the logits and the labels.
		Args:
		logits: Logits tensor, float - [batch_size, NUM_CLASSES].
		labels: Labels tensor, int32 - [batch_size].
		Returns:
		loss: Loss tensor of type float.
		"""
		prob = tf.nn.softmax(output)
		labels = tf.to_int64(labels)
		cross_entropy = tf.nn.sparse_softmax_cross_entropy_with_logits(output, labels, name='xentropy')
		cross_entropy_mean = tf.reduce_mean(cross_entropy, name='cross_entropy')
		tf.add_to_collection('losses', cross_entropy_mean)
		return tf.add_n(tf.get_collection('losses'), name='total_loss'), cross_entropy_mean, prob

	def print_training(self, step, loss, total_correct, Ncase, duration):
		denom=max(int(Ncase/self.batch_size),1)
		print("step: ", "%7d"%step, "  duration: ", "%.5f"%duration,  "  train loss: ", "%.10f"%(float(loss)/denom),"accu:  %.5f"%(float(total_correct)/(denom*self.batch_size)))
		return

	def train_prepare(self,  continue_training =False):
		"""Train for a number of steps."""
		with tf.Graph().as_default(), tf.device('/job:localhost/replica:0/task:0/gpu:1'):
			self.embeds_placeholder, self.labels_placeholder = self.placeholder_inputs(self.batch_size)
			self.output = self.inference(self.embeds_placeholder, self.hidden1, self.hidden2, self.hidden3)
			self.total_loss, self.loss, self.prob = self.loss_op(self.output, self.labels_placeholder)
			self.train_op = self.training(self.total_loss, self.learning_rate, self.momentum)
			self.summary_op = tf.merge_all_summaries()
			init = tf.initialize_all_variables()
			self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True))
			self.saver = tf.train.Saver()
			try: # I think this may be broken
				chkfiles = [x for x in os.listdir(self.train_dir) if (x.count('chk')>0 and x.count('meta')==0)]
				if (len(chkfiles)>0):
					most_recent_chk_file=chkfiles[0]
					print("Restoring training from Checkpoint: ",most_recent_chk_file)
					self.saver.restore(self.sess, self.train_dir+'/'+most_recent_chk_file)
			except Exception as Ex:
				print("Restore Failed",Ex)
				pass
			self.summary_writer = tf.train.SummaryWriter(self.train_dir, self.sess.graph)
			self.sess.run(init)
		return

	def test(self, step):
		Ncase_test = self.TData.NTest
		test_loss =  0.0
		test_correct = 0.
		test_start_time = time.time()
		test_loss = None
		feed_dict = None
		for  ministep in range (0, int(Ncase_test/self.batch_size)):
			batch_data=self.TData.GetTestBatch(  self.batch_size, ministep)
			feed_dict = self.fill_feed_dict(batch_data, self.embeds_placeholder, self.labels_placeholder)
			loss_value, prob_value, test_correct_num = self.sess.run([ self.loss, self.prob, self.correct],  feed_dict=feed_dict)
			test_loss = test_loss + loss_value
			test_correct = test_correct + test_correct_num
			duration = time.time() - test_start_time
			print("testing...")
			self.print_training(step, test_loss, test_correct, Ncase_test, duration)
		return test_loss, feed_dict


class MolInstance_fc_sqdiff(MolInstance):
	def __init__(self, TData_,  Name_=None):
		self.NetType = "fc_sqdiff"
		MolInstance.__init__(self, TData_,  Name_)
		self.name = "Mol_"+self.TData.name+"_"+self.TData.dig.name+"_"+str(self.TData.order)+"_"+self.NetType
		self.train_dir = './networks/'+self.name
		self.hidden1 = 500
		self.hidden2 = 500
		self.hidden3 = 500
		self.inshape = np.prod(self.TData.dig.eshape)
		self.outshape = np.prod(self.TData.dig.lshape)
#		self.inshape = self.TData.scratch_inputs.shape[1]
		self.summary_op =None
		self.summary_writer=None
		self.check=None 
		self.name = "Mol_"+self.TData.name+"_"+self.TData.dig.name+"_"+str(self.TData.order)+"_"+self.NetType

	def evaluate(self, eval_input):
		# Check sanity of input
		MolInstance.evaluate(self, eval_input)
		eval_input_ = eval_input
		if (self.PreparedFor>eval_input.shape[0]):
			eval_input_ =np.copy(eval_input)
			eval_input_.resize((self.PreparedFor,eval_input.shape[1]))
			# pad with zeros
		eval_labels = np.zeros((self.PreparedFor,1))  # dummy labels
		batch_data = [eval_input_, eval_labels]
		#images_placeholder, labels_placeholder = self.placeholder_inputs(Ncase) Made by Prepare()
		feed_dict = self.fill_feed_dict(batch_data,self.embeds_placeholder,self.labels_placeholder)
		tmp, gradient =  (self.sess.run([self.output, self.gradient], feed_dict=feed_dict))
		if (not np.all(np.isfinite(tmp))):
			print("TFsession returned garbage")
			print("TFInputs",eval_input) #If it's still a problem here use tf.Print version of the graph.
		if (self.PreparedFor>eval_input.shape[0]):
			return tmp[:eval_input.shape[0]], gradient[:eval_input.shape[0]]
		return tmp, gradient

	def Prepare(self, eval_input, Ncase=125000):
		self.Clean()
		# Always prepare for at least 125,000 cases which is a 50x50x50 grid.
		eval_labels = np.zeros(Ncase)  # dummy labels
		with tf.Graph().as_default(), tf.device('/job:localhost/replica:0/task:0/gpu:1'):
			self.embeds_placeholder, self.labels_placeholder = self.placeholder_inputs(Ncase)
			self.output = self.inference(self.embeds_placeholder, self.hidden1, self.hidden2, self.hidden3)
			print ("type of self.embeds_placeholder:", type(self.embeds_placeholder))
			self.gradient = tf.gradients(self.output, self.embeds_placeholder)[0]
			self.saver = tf.train.Saver()
			self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True))
			self.saver.restore(self.sess, self.chk_file)
		self.PreparedFor = Ncase
		return

	def SaveAndClose(self):
		MolInstance.SaveAndClose(self)
		self.summary_op =None
		self.summary_writer=None
		self.check=None
		self.label_pl = None
		self.mats_pl = None
		self.inp_pl = None
		return

	def placeholder_inputs(self, batch_size):
		"""Generate placeholder variables to represent the input tensors.
		These placeholders are used as inputs by the rest of the model building
		code and will be fed from the downloaded data in the .run() loop, below.
		Args:
		batch_size: The batch size will be baked into both placeholders.
		Returns:
		images_placeholder: Images placeholder.
		labels_placeholder: Labels placeholder.
		"""
		# Note that the shapes of the placeholders match the shapes of the full
		# image and label tensors, except the first dimension is now batch_size
		# rather than the full size of the train or test data sets.
		inputs_pl = tf.placeholder(tf.float32, shape=(batch_size,self.inshape)) # JAP : Careful about the shapes... should be flat for now.
		outputs_pl = tf.placeholder(tf.float32, shape=(batch_size, self.outshape))
		return inputs_pl, outputs_pl

	def loss_op(self, output, labels):
		diff  = tf.subtract(output, labels)
		loss = tf.nn.l2_loss(diff)
		tf.add_to_collection('losses', loss)
		return tf.add_n(tf.get_collection('losses'), name='total_loss'), loss

	def test(self, step):
		Ncase_test = self.TData.NTest
		test_loss =  0.0
		test_correct = 0.
		test_start_time = time.time()
		for  ministep in range (0, int(Ncase_test/self.batch_size)):
			batch_data=self.TData.GetTestBatch( self.batch_size, ministep)
			batch_data=self.PrepareData(batch_data)
			feed_dict = self.fill_feed_dict(batch_data, self.embeds_placeholder, self.labels_placeholder)
			total_loss_value, loss_value, output_value  = self.sess.run([self.total_loss,  self.loss, self.output],  feed_dict=feed_dict)
			test_loss = test_loss + loss_value
			duration = time.time() - test_start_time
		print("testing...")
		self.print_training(step, test_loss,  Ncase_test, duration)
		return test_loss, feed_dict

	def train_prepare(self,  continue_training =False):
		"""Train for a number of steps."""
		with tf.Graph().as_default(), tf.device('/job:localhost/replica:0/task:0/gpu:1'):
			self.embeds_placeholder, self.labels_placeholder = self.placeholder_inputs(self.batch_size)
			self.output = self.inference(self.embeds_placeholder, self.hidden1, self.hidden2, self.hidden3)
			self.total_loss, self.loss = self.loss_op(self.output, self.labels_placeholder)
			self.train_op = self.training(self.total_loss, self.learning_rate, self.momentum)
			self.summary_op = tf.merge_all_summaries()
			init = tf.initialize_all_variables()
			self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True))
			self.saver = tf.train.Saver()
			try: # I think this may be broken
				chkfiles = [x for x in os.listdir(self.train_dir) if (x.count('chk')>0 and x.count('meta')==0)]
				if (len(chkfiles)>0):
					most_recent_chk_file=chkfiles[0]
					print("Restoring training from Checkpoint: ",most_recent_chk_file)
					self.saver.restore(self.sess, self.train_dir+'/'+most_recent_chk_file)
			except Exception as Ex:
				print("Restore Failed",Ex)
				pass
			self.summary_writer = tf.train.SummaryWriter(self.train_dir, self.sess.graph)
			self.sess.run(init)
			return

	def PrepareData(self, batch_data):
		if (batch_data[0].shape[0]==self.batch_size):
			batch_data=[batch_data[0], batch_data[1].reshape((batch_data[1].shape[0],self.outshape))]
		elif (batch_data[0].shape[0] < self.batch_size):
			batch_data=[batch_data[0], batch_data[1].reshape((batch_data[1].shape[0],self.outshape))]
			tmp_input = np.copy(batch_data[0])
			tmp_output = np.copy(batch_data[1])
			tmp_input.resize((self.batch_size,  batch_data[0].shape[1]))
			tmp_output.resize((self.batch_size,  batch_data[1].shape[1]))
			batch_data=[ tmp_input, tmp_output]
		return batch_data

	def train_step(self,step):
		Ncase_train = self.TData.NTrain
		start_time = time.time()
		train_loss =  0.0
		for ministep in range (0, int(Ncase_train/self.batch_size)):
			batch_data=self.TData.GetTrainBatch( self.batch_size) #advances the case pointer in TData...
			batch_data=self.PrepareData(batch_data)
			feed_dict = self.fill_feed_dict(batch_data, self.embeds_placeholder, self.labels_placeholder)
			_, total_loss_value, loss_value  = self.sess.run([self.train_op, self.total_loss, self.loss], feed_dict=feed_dict)
			train_loss = train_loss + loss_value
			duration = time.time() - start_time
		self.print_training(step, train_loss, Ncase_train, duration)
		return

class MolInstance_fc_sqdiff_BP(MolInstance_fc_sqdiff):
	"""
		An instance of A fully connected Behler-Parinello network.
		Which requires a TensorMolData to train/execute.
	"""
	def __init__(self, TData_, Name_=None):
		"""
		Raise a Behler-Parinello TensorFlow instance.

		Args:
			TData_: A TensorMolData instance.
			Name_: A name for this instance.
		"""
		self.NetType = "fc_sqdiff_BP"
		MolInstance.__init__(self, TData_,  Name_)
		if Name_:  # already loaded 
			return
		self.name = "Mol_"+self.TData.name+"_"+self.TData.dig.name+"_"+str(self.TData.order)+"_"+self.NetType
		print ("instance name:", self.name)
		self.train_dir = './networks/'+self.name
		self.learning_rate = 0.00001
		self.momentum = 0.95
		# Using multidimensional inputs creates all sorts of issues; for the time being only support flat inputs.
		self.inshape = np.prod(self.TData.dig.eshape)
		print("MolInstance_fc_sqdiff_BP.inshape: ",self.inshape)
		self.eles = self.TData.eles
		self.n_eles = len(self.eles)
		self.MeanStoich = self.TData.MeanStoich # Average stoichiometry of a molecule.
		self.MeanNumAtoms = np.sum(self.MeanStoich)
		self.AtomBranchNames=[] # a list of the layers named in each atom branch

		self.inp_pl=None
		self.mats_pl=None
		self.label_pl=None
		self.atom_outputs = None

		# self.batch_size is still the number of inputs in a batch.
		#self.batch_size = 4000
		self.batch_size = 10000
		#self.batch_size = 50000
		self.batch_size_output = 0
		self.hidden1 = 200
		self.hidden2 = 200
		self.hidden3 = 200
		#self.hidden1 = 1000
		#self.hidden2 = 1000
		#self.hidden3 = 1000
		self.summary_op =None
		self.summary_writer=None

        def Clean(self):
		Instance.Clean(self)
		self.summary_op =None
                self.summary_writer=None
		self.inp_pl=None
		self.check = None
                self.mats_pl=None
                self.label_pl=None
		self.summary_op =None
                self.summary_writer=None
		self.atom_outputs = None
                return


	def train_prepare(self,  continue_training =False):
		"""
		Get placeholders, graph and losses in order to begin training.
		Also assigns the desired padding.

		Args:
			continue_training: should read the graph variables from a saved checkpoint.
		"""
		self.TData.LoadDataToScratch()
		self.MeanNumAtoms = self.TData.MeanNumAtoms
		print("self.MeanNumAtoms: ",self.MeanNumAtoms)
		# allow for 120% of required output space, since it's cheaper than input space to be padded by zeros.
		self.batch_size_output = int(1.5*self.batch_size/self.MeanNumAtoms)
		print ("self.batch_size_output:", self.batch_size_output)
		#self.TData.CheckBPBatchsizes(self.batch_size, self.batch_size_output)
		print("Assigned batch input size: ",self.batch_size)
		print("Assigned batch output size: ",self.batch_size_output)
		with tf.Graph().as_default(), tf.device('/job:localhost/replica:0/task:0/gpu:1'):
			self.inp_pl=[]
			self.mats_pl=[]
			for e in range(len(self.eles)):
				self.inp_pl.append(tf.placeholder(tf.float32, shape=tuple([None,self.inshape])))
				self.mats_pl.append(tf.placeholder(tf.float32, shape=tuple([None,self.batch_size_output])))
			self.label_pl = tf.placeholder(tf.float32, shape=tuple([self.batch_size_output]))
			self.output, self.atom_outputs = self.inference(self.inp_pl, self.mats_pl)
			self.check = tf.add_check_numerics_ops()
			self.total_loss, self.loss = self.loss_op(self.output, self.label_pl)
			self.train_op = self.training(self.total_loss, self.learning_rate, self.momentum)
			self.summary_op = tf.summary.merge_all()
			init = tf.global_variables_initializer()
			#self.summary_op = tf.summary.merge_all()
			#init = tf.global_variables_initializer()
			self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True))
			self.saver = tf.train.Saver()
#			try: # I think this may be broken
#				chkfiles = [x for x in os.listdir(self.train_dir) if (x.count('chk')>0 and x.count('meta')==0)]
#				if (len(chkfiles)>0):
#						most_recent_chk_file=chkfiles[0]
#						print("Restoring training from Checkpoint: ",most_recent_chk_file)
#						self.saver.restore(self.sess, self.train_dir+'/'+most_recent_chk_file)
#			except Exception as Ex:
#				print("Restore Failed",Ex)
#				pass
			self.summary_writer = tf.summary.FileWriter(self.train_dir, self.sess.graph)
			self.sess.run(init)
		return

	def loss_op(self, output, labels):
		diff  = tf.subtract(output, labels)
		#tf.Print(diff, [diff], message="This is diff: ",first_n=10000000,summarize=100000000)
		#tf.Print(labels, [labels], message="This is labels: ",first_n=10000000,summarize=100000000)
		loss = tf.nn.l2_loss(diff)
		tf.add_to_collection('losses', loss)
		return tf.add_n(tf.get_collection('losses'), name='total_loss'), loss

	def inference(self, inp_pl, mats_pl):
		"""
		Builds a Behler-Parinello graph

		Args:
				inp_pl: a list of (num_of atom type X flattened input shape) matrix of input cases.
				mats_pl: a list of (num_of atom type X batchsize) matrices which linearly combines the elements
		Returns:
			The BP graph output
		"""
		# convert the index matrix from bool to float
		branches=[]
		atom_outputs = []
		hidden1_units=self.hidden1
		hidden2_units=self.hidden2
		hidden3_units=self.hidden3
		output = tf.zeros([self.batch_size_output])
		nrm1=1.0/(10+math.sqrt(float(self.inshape)))
		nrm2=1.0/(10+math.sqrt(float(hidden1_units)))
		nrm3=1.0/(10+math.sqrt(float(hidden2_units)))
		nrm4=1.0/(10+math.sqrt(float(hidden3_units)))
		print("Norms:", nrm1,nrm2,nrm3)
		#print(inp_pl)
		#tf.Print(inp_pl, [inp_pl], message="This is input: ",first_n=10000000,summarize=100000000)
		#tf.Print(bnds_pl, [bnds_pl], message="bnds_pl: ",first_n=10000000,summarize=100000000)
		#tf.Print(mats_pl, [mats_pl], message="mats_pl: ",first_n=10000000,summarize=100000000)
		for e in range(len(self.eles)):
			branches.append([])
			inputs = inp_pl[e]
			mats = mats_pl[e]
			shp_in = tf.shape(inputs)
			#tf.Print(tf.to_float(shp_in), [tf.to_float(shp_in)], message="This is inputs: ",first_n=10000000,summarize=100000000)
			with tf.name_scope(str(self.eles[e])+'_hidden_1'):
				weights = self._variable_with_weight_decay(var_name='weights', var_shape=[self.inshape, hidden1_units], var_stddev=nrm1, var_wd=0.001)
				biases = tf.Variable(tf.zeros([hidden1_units]), name='biases')
				branches[-1].append(tf.nn.relu(tf.matmul(inputs, weights) + biases))
			with tf.name_scope(str(self.eles[e])+'_hidden_2'):
				weights = self._variable_with_weight_decay(var_name='weights', var_shape=[hidden1_units, hidden2_units], var_stddev=nrm2, var_wd=0.001)
				biases = tf.Variable(tf.zeros([hidden2_units]), name='biases')
				branches[-1].append(tf.nn.relu(tf.matmul(branches[-1][-1], weights) + biases))
			with tf.name_scope(str(self.eles[e])+'_hidden_3'):
                                weights = self._variable_with_weight_decay(var_name='weights', var_shape=[hidden2_units, hidden3_units], var_stddev=nrm3, var_wd=0.001)
                                biases = tf.Variable(tf.zeros([hidden3_units]), name='biases')
                                branches[-1].append(tf.nn.relu(tf.matmul(branches[-1][-1], weights) + biases))
				#tf.Print(branches[-1], [branches[-1]], message="This is layer 2: ",first_n=10000000,summarize=100000000)
			with tf.name_scope(str(self.eles[e])+'_regression_linear'):
				shp = tf.shape(inputs)
				weights = self._variable_with_weight_decay(var_name='weights', var_shape=[hidden3_units, 1], var_stddev=nrm4, var_wd=None)
				biases = tf.Variable(tf.zeros([1]), name='biases')
				branches[-1].append(tf.matmul(branches[-1][-1], weights) + biases)
				shp_out = tf.shape(branches[-1][-1])
				cut = tf.slice(branches[-1][-1],[0,0],[shp_out[0],1])
				#tf.Print(tf.to_float(shp_out), [tf.to_float(shp_out)], message="This is outshape: ",first_n=10000000,summarize=100000000)
				rshp = tf.reshape(cut,[1,shp_out[0]])
				atom_outputs.append(rshp)
				tmp = tf.matmul(rshp,mats)
				#self.atom_outputs[e] = tmp
				output = tf.add(output,tmp)
		tf.verify_tensor_all_finite(output,"Nan in output!!!")
		#tf.Print(output, [output], message="This is output: ",first_n=10000000,summarize=100000000)
		return output, atom_outputs

	def fill_feed_dict(self, batch_data):
		"""
		Fill the tensorflow feed dictionary.

		Args:
			batch_data: a list of numpy arrays containing inputs, bounds, matrices and desired energies in that order.
			and placeholders to be assigned.

		Returns:
			Filled feed dictionary.
		"""
		# Don't eat shit.
		for e in range(len(self.eles)):
			if (not np.all(np.isfinite(batch_data[0][e]),axis=(0,1))):
				print("I was fed shit1")
				raise Exception("DontEatShit")
			if (not np.all(np.isfinite(batch_data[1][e]),axis=(0,1))):
				print("I was fed shit3")
				raise Exception("DontEatShit")
		if (not np.all(np.isfinite(batch_data[2]),axis=(0))):
			print("I was fed shit4")
			raise Exception("DontEatShit")
		#for data in batch_data[0]:
		#	print ("batch_data[0] shape:", data.shape)
		#for data in batch_data[1]:
                #        print ("batch_data[1] shape:", data.shape)
		feed_dict={i: d for i, d in zip(self.inp_pl+self.mats_pl+[self.label_pl], batch_data[0]+batch_data[1]+[batch_data[2]])}
		#print ("feed_dict\n\n", feed_dict)
		return feed_dict

	def train_step(self, step):
		"""
		Perform a single training step (complete processing of all input), using minibatches of size self.batch_size

		Args:
			step: the index of this step.
		"""
		Ncase_train = self.TData.NTrain
		start_time = time.time()
		train_loss =  0.0
		num_of_mols = 0
		for ministep in range (0, int(Ncase_train/self.batch_size)):
			#print ("ministep: ", ministep, " Ncase_train:", Ncase_train, " self.batch_size", self.batch_size)
			batch_data = self.TData.GetTrainBatch(self.batch_size,self.batch_size_output)
			actual_mols  = np.count_nonzero(batch_data[2])
			dump_, dump_2, total_loss_value, loss_value, mol_output = self.sess.run([self.check, self.train_op, self.total_loss, self.loss, self.output], feed_dict=self.fill_feed_dict(batch_data))
			#print ("train pred:", mol_output, " accurate:", batch_data[2])
			train_loss = train_loss + loss_value
			duration = time.time() - start_time
			num_of_mols += actual_mols
			#print ("atom_outputs:", atom_outputs, " mol outputs:", mol_output)
			#print ("atom_outputs shape:", atom_outputs[0].shape, " mol outputs", mol_output.shape)
		#print("train diff:", (mol_output[0]-batch_data[2])[:actual_mols], np.sum(np.square((mol_output[0]-batch_data[2])[:actual_mols])))
		#print ("train_loss:", train_loss, " Ncase_train:", Ncase_train, train_loss/num_of_mols)
		#print ("diff:", mol_output - batch_data[2], " shape:", mol_output.shape)
		self.print_training(step, train_loss, num_of_mols, duration)
		return

	def test(self, step):   # testing in the training
		"""
		Perform a single test step (complete processing of all input), using minibatches of size self.batch_size

		Args:
			step: the index of this step.
		"""
		test_loss =  0.0
		start_time = time.time()
		Ncase_test = self.TData.NTest
		num_of_mols = 0


		for ministep in range (0, int(Ncase_test/self.batch_size)):
			#print ("ministep:", ministep)
			batch_data=self.TData.GetTestBatch(self.batch_size,self.batch_size_output)
			feed_dict=self.fill_feed_dict(batch_data)
			actual_mols  = np.count_nonzero(batch_data[2])
			preds, total_loss_value, loss_value, mol_output, atom_outputs = self.sess.run([self.output,self.total_loss, self.loss, self.output, self.atom_outputs],  feed_dict=feed_dict)
			test_loss += loss_value
			num_of_mols += actual_mols

		#print("preds:", preds[0][:actual_mols], " accurate:", batch_data[2][:actual_mols])
		duration = time.time() - start_time
		#print ("preds:", preds, " label:", batch_data[2])
		#print ("diff:", preds - batch_data[2])
		print( "testing...")
		self.print_training(step, test_loss, num_of_mols, duration)
		#self.TData.dig.EvaluateTestOutputs(batch_data[2],preds)
		return test_loss, feed_dict


	def test_after_training(self, step):   # testing in the training
		"""
		Perform a single test step (complete processing of all input), using minibatches of size self.batch_size

		Args:
			step: the index of this step.
		"""
		test_loss =  0.0
		start_time = time.time()
		Ncase_test = self.TData.NTest
		num_of_mols = 0

		all_atoms = []
		bond_length = []
		for i in range (0, len(self.eles)):
			all_atoms.append([])
			bond_length.append([])
		all_mols_nn = []
		all_mols_acc = []

		for ministep in range (0, int(Ncase_test/self.batch_size)):
			batch_data=self.TData.GetTestBatch(self.batch_size,self.batch_size_output)
			feed_dict=self.fill_feed_dict(batch_data)
			actual_mols  = np.count_nonzero(batch_data[2])
			preds, total_loss_value, loss_value, mol_output, atom_outputs = self.sess.run([self.output,self.total_loss, self.loss, self.output, self.atom_outputs],  feed_dict=feed_dict)
			test_loss += loss_value
			num_of_mols += actual_mols

			print ("actual_mols:", actual_mols)
			all_mols_nn += list(preds[np.nonzero(preds)])
			all_mols_acc += list(batch_data[2][np.nonzero(batch_data[2])])
			#print ("length:", len(atom_outputs))
			for atom_index in range (0,len(self.eles)):
				all_atoms[atom_index] += list(atom_outputs[atom_index][0])
				bond_length[atom_index] += list(1.0/batch_data[0][atom_index][:,-1])
				#print ("atom_index:", atom_index, len(atom_outputs[atom_index][0]))
		test_result = dict()
		test_result['atoms'] = all_atoms
		test_result['nn'] = all_mols_nn
		test_result['acc'] = all_mols_acc
		test_result['length'] = bond_length
		f = open("test_result_energy_cleaned_connectedbond_angle_for_test_writting_all_mol.dat","wb")
		pickle.dump(test_result, f)
		f.close()

		#print("preds:", preds[0][:actual_mols], " accurate:", batch_data[2][:actual_mols])
		duration = time.time() - start_time
		#print ("preds:", preds, " label:", batch_data[2])
		#print ("diff:", preds - batch_data[2])
		print( "testing...")
		self.print_training(step, test_loss, num_of_mols, duration)
		#self.TData.dig.EvaluateTestOutputs(batch_data[2],preds)
		return test_loss, feed_dict


        def print_training(self, step, loss, Ncase, duration, Train=True):
                if Train:
                        print("step: ", "%7d"%step, "  duration: ", "%.5f"%duration,  "  train loss: ", "%.10f"%(float(loss)/(Ncase)))
                else:
                        print("step: ", "%7d"%step, "  duration: ", "%.5f"%duration,  "  test loss: ", "%.10f"%(float(loss)/(NCase)))
                return


	def continue_training(self, mxsteps):
		self.Eval_Prepare()
		test_loss , feed_dict = self.test(-1)
                test_freq = 1
                mini_test_loss = test_loss
                for step in  range (0, mxsteps+1):
                        self.train_step(step)
                        if step%test_freq==0 and step!=0 :
                                test_loss, feed_dict = self.test(step)
                                if test_loss < mini_test_loss:
                                        mini_test_loss = test_loss
                                        self.save_chk(step, feed_dict)
                self.SaveAndClose()	
		return 	

        def evaluate(self, batch_data):   #this need to be modified 
                # Check sanity of input
		nmol = batch_data[2].shape[0]
		print ("nmol:", batch_data[2].shape[0])
		self.batch_size_output = nmol
                if not self.sess:
			t = time.time()
                        print ("loading the session..")
                        self.Eval_Prepare()
			print ("loading time cost: ", time.time() -t, " second")
		feed_dict=self.fill_feed_dict(batch_data)
		preds, total_loss_value, loss_value, mol_output, atom_outputs = self.sess.run([self.output,self.total_loss, self.loss, self.output, self.atom_outputs],  feed_dict=feed_dict)
                return mol_output, atom_outputs

	def Eval_Prepare(self):
                #eval_labels = np.zeros(Ncase)  # dummy labels
                with tf.Graph().as_default(), tf.device('/job:localhost/replica:0/task:0/gpu:1'):
                        self.inp_pl=[]
                        self.mats_pl=[]
                        for e in range(len(self.eles)):
                                self.inp_pl.append(tf.placeholder(tf.float32, shape=tuple([None,self.inshape])))
                                self.mats_pl.append(tf.placeholder(tf.float32, shape=tuple([None, self.batch_size_output])))
                        self.label_pl = tf.placeholder(tf.float32, shape=tuple([self.batch_size_output]))
                        self.output, self.atom_outputs = self.inference(self.inp_pl, self.mats_pl)
                        self.check = tf.add_check_numerics_ops()
                        self.total_loss, self.loss = self.loss_op(self.output, self.label_pl)
                        self.train_op = self.training(self.total_loss, self.learning_rate, self.momentum)
                        self.summary_op = tf.summary.merge_all()
                        init = tf.global_variables_initializer()
                        self.saver = tf.train.Saver()
                        self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True))
                        self.saver.restore(self.sess, self.chk_file)
                return


        def Prepare(self):
                #eval_labels = np.zeros(Ncase)  # dummy labels
                self.MeanNumAtoms = self.TData.MeanNumAtoms
                self.batch_size_output = int(1.5*self.batch_size/self.MeanNumAtoms)
                with tf.Graph().as_default(), tf.device('/job:localhost/replica:0/task:0/gpu:1'):
                        self.inp_pl=[]
                        self.mats_pl=[]
                        for e in range(len(self.eles)):
                                self.inp_pl.append(tf.placeholder(tf.float32, shape=tuple([None,self.inshape])))
                                self.mats_pl.append(tf.placeholder(tf.float32, shape=tuple([None,self.batch_size_output])))
                        self.label_pl = tf.placeholder(tf.float32, shape=tuple([self.batch_size_output]))
                        self.output, self.atom_outputs = self.inference(self.inp_pl, self.mats_pl)
                        self.check = tf.add_check_numerics_ops()
                        self.total_loss, self.loss = self.loss_op(self.output, self.label_pl)
                        self.train_op = self.training(self.total_loss, self.learning_rate, self.momentum)
                        self.summary_op = tf.summary.merge_all()
                        init = tf.global_variables_initializer()
			self.saver = tf.train.Saver()
                        self.sess = tf.Session(config=tf.ConfigProto(allow_soft_placement=True))
                        self.saver.restore(self.sess, self.chk_file)
                return

