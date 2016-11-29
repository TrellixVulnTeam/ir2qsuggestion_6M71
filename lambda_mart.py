import numpy as np
import logging
import pandas as pd
from sklearn.model_selection import cross_val_score
import sklearn.datasets as ds
from rankpy.queries import Queries
from rankpy.models import LambdaMART
from collections import Counter
import operator
import sessionizer as sn
import random
import math
import itertools
import features.adj as ad
import features.cossimilar as cs
import features.length as lg
import features.lengthdiff as ld
import features.levenstein as levs


sessionize = sn.Sessionizer()
sessions = sn.Sessionizer.get_sessions(sessionize)

adj = ad.ADJ()
lev = levs.Levenshtein()
lendif = ld.LengthDiff()
leng = lg.Length()
coss = cs.CosineSimilarity()


def get_query_index_pointers(dataset):
    query_index_pointers = []
    lower_bound = 0
    for i in range(dataset.shape[0]/20 + 1):
        query_index_pointer = lower_bound
        query_index_pointers.append(query_index_pointer)
        lower_bound += 20
    query_index_pointers = np.array(query_index_pointers)
    return query_index_pointers

# def get_MRR():


def lambdaMart(data, experiment_string):
    # Turn on logging.
    logging.basicConfig(format='%(asctime)s : %(message)s', level=logging.INFO)

    # divide set into train, val and test set
    # 55% train
    # 20% validation
    # 25% test
    query_index_pointers = get_query_index_pointers(data[:,0])

    train_part_pointer = int(math.floor(query_index_pointers.shape[0]*0.55))
    training_pointers, test_val_pointers = query_index_pointers[:train_part_pointer], query_index_pointers[train_part_pointer-1:]
    val_part = int(math.floor(test_val_pointers.shape[0] * 0.40))
    training_length = training_pointers.shape[0]
    upper_bound_train = training_pointers[training_length - 1]
    validation_pointers = test_val_pointers[:val_part]
    validation_length = validation_pointers.shape[0]
    upper_bound_val = validation_pointers[validation_length - 1]
    test_pointers = test_val_pointers[val_part-1:]



    training_queries = data[:upper_bound_train,:]

    validation_queries, test_queries = data[upper_bound_train:upper_bound_val,:], data[upper_bound_val:,:]


    logging.info('================================================================================')


    # Set them to queries
    logging.info('Creating Training queries')
    training_targets = pd.DataFrame(training_queries[:,:1]).astype(np.float32)
    training_features = pd.DataFrame(training_queries[:,1:-1]).astype(np.float32)
    training_queries = Queries(training_features, training_targets, training_pointers)

    logging.info('Creating Validation queries')
    validation_targets = pd.DataFrame(validation_queries[:, :1]).astype(np.float32)
    validation_features = pd.DataFrame(validation_queries[:, 1:-1]).astype(np.float32)
    validation_pointers = validation_pointers - upper_bound_train
    validation_queries = Queries(validation_features, validation_targets, validation_pointers)

    logging.info('Creating Test queries')
    test_targets = pd.DataFrame(test_queries[:, :1]).astype(np.float32)
    test_features = pd.DataFrame(test_queries[:, 1:-1]).astype(np.float32)
    test_pointers = test_pointers - (upper_bound_val)
    test_queries = Queries(test_features, test_targets, test_pointers)

    logging.info('================================================================================')

    # Print basic info about query datasets.
    logging.info('Train queries: %s' % training_queries)
    logging.info('Valid queries: %s' % validation_queries)
    logging.info('Test queries: %s' %test_queries)

    logging.info('================================================================================')

    model = LambdaMART(metric='nDCG@20', n_estimators=500, subsample=0.5)
    logging.info("model is made")
    model.fit(training_queries, validation_queries=validation_queries)

    logging.info('================================================================================')

    logging.info('%s on the test queries: %.8f'
                 % (model.metric, model.evaluate(test_queries, n_jobs=-1)))

    model.save('LambdaMART_L7_S0.1_E50_' + experiment_string + model.metric)


def create_features(anchor_query, session):
    lev_features = []
    lendif_features = []
    leng_features = []
    coss_features = []

    session_length = len(session)
    adj_dict = adj.adj_function(anchor_query)
    highest_adj_queries = adj_dict['adj_queries']
    sugg_features = adj_dict['absfreq']
    for query in highest_adj_queries:
        if session_length > 11:
            #Take the features of the 10 most recent queries (contextual features)
            lev_features_per_query = lev.calculate_feature(query, session[-11:-1])
            lev_features.append(lev_features_per_query)
            lendif_per_query = lendif.calculate_feature(query, session[-11:-1])
            lendif_features.append(lendif_per_query)
            leng_per_query = leng.calculate_feature(query, session[-11:-1])
            leng_features.append(leng_per_query)
            coss_per_query = coss.calculate_feature(query, session[-11:-1])
            coss_features.append(coss_per_query)
        else:
            #If there are no 10 most recent queries: add zero padding at the end
            lev_features_per_query = lev.calculate_feature(query, session[:session_length-1])
            lendif_per_query = lendif.calculate_feature(query, session[:session_length-1])
            leng_per_query = leng.calculate_feature(query, session[:session_length-1])
            coss_per_query = coss.calculate_feature(query, session[:session_length-1])
            length_difference = 10 - (session_length-1)
            for i in range(length_difference):
                lev_features_per_query.append(0)
                lendif_per_query.append(0)
                leng_per_query.append(0)
                coss_per_query.append(0)
            lev_features.append(lev_features_per_query)
            lendif_features.append(lendif_per_query)
            leng_features.append(leng_per_query)
            coss_features.append(coss_per_query)
    features = np.vstack((np.array(sugg_features), np.transpose(np.array(lev_features))))
    features = np.vstack((features, np.transpose(np.array(lendif_features))))
    features = np.vstack((features, np.transpose(np.array(leng_features))))
    features = np.vstack((features, np.transpose(np.array(coss_features))))
    return features, highest_adj_queries


def next_query_prediction(sessions, experiment_string):
    used_sess = 0
    corresponding_queries = []
    for i,session in enumerate(sessions):
        if i < 1000:
            session_length = len(session)
            # get anchor query and target query from session
            anchor_query = session[session_length-2]
            target_query = session[session_length-1]
            # extract 20 queries with the highest ADJ score (most likely to follow the anchor query in the data)
            features, highest_adj_queries = create_features(anchor_query, session)
            # target Query is the positive candidate if it is in the 20 queries, the other 19 are negative candidates
            if target_query in highest_adj_queries and 19 < len(highest_adj_queries):
                print("Session: " + str(i))
                target_vector = -1 * np.ones(len(highest_adj_queries))
                [target_query_index] = [q for q, x in enumerate(highest_adj_queries) if x == target_query]
                target_vector[target_query_index] = 1
                # then add the session to the train, val, test data
                indexes = np.array(range(0,len(highest_adj_queries)))
                sess_data = np.vstack((np.transpose(target_vector), features))
                sess_data = np.vstack((sess_data, np.transpose(indexes)))
                if used_sess == 0:
                    lambdamart_data = sess_data
                    used_sess += 1
                else:
                    lambdamart_data = np.hstack((lambdamart_data, sess_data))
                    used_sess += 1
            else:
                continue
    results = lambdaMart(np.transpose(lambdamart_data), experiment_string)
    print("---" * 30)
    print("used sessions:" + str(used_sess))
    return results, corresponding_queries




def shorten_query(query):
    query = query.rsplit(' ', 1)[0]
    return query


def make_long_tail_set(sessions, background_set, experiment_string):
    used_sess = 0
    corresponding_queries = []
    for i, session in enumerate(sessions):
        if i < 1000:
            session_length = len(session)
            # get anchor query and target query from session
            anchor_query = session[session_length - 2]
            target_query = session[session_length - 1]
            # Cannot use ADJ
            # Therefore iteratively shorten anchor query by dropping terms
            # until we have a query that appears in the Background data
            for j in range(len(anchor_query.split())):
                if anchor_query not in background_set and len(anchor_query.split()) != 1:
                    anchor_query = shorten_query(anchor_query)
                else:
                    features, highest_adj_queries = create_features(anchor_query, session)
                    # target Query is the positive candidate if it is in the 20 queries, the other 19 are negative candidates
                    if target_query in highest_adj_queries and 19 < len(highest_adj_queries):
                        print("Session: " + str(i))
                        target_vector = -1 * np.ones(len(highest_adj_queries))
                        [target_query_index] = [q for q, x in enumerate(highest_adj_queries) if x == target_query]
                        target_vector[target_query_index] = 1
                        # then add the session to the train, val, test data
                        indexes = np.array(range(0, len(highest_adj_queries)))
                        sess_data = np.vstack((np.transpose(target_vector), features))
                        sess_data = np.vstack((sess_data, np.transpose(indexes)))
                        if used_sess == 0:
                            lambdamart_data = sess_data
                            used_sess += 1
                        else:
                            lambdamart_data = np.hstack((lambdamart_data, sess_data))
                            used_sess += 1
                    else:
                        continue
    print("---" * 30)
    print("used sessions:" + str(used_sess))
    results = lambdaMart(np.transpose(lambdamart_data), experiment_string)
    return results, corresponding_queries

def count_query_frequency(query_list):
    noise_freq = []
    counts = Counter(np.array(query_list))
    highest_100 = counts.most_common(100)
    for i in range(100):
        noise_freq.append(highest_100[i][1])
    return highest_100, noise_freq


def get_random_noise(highest_100, noise_prob):
    total = sum(w for w in noise_prob)
    r = random.uniform(0, total)
    upto = 0
    for index, w in enumerate(noise_prob):
        if upto + w >= r:
            return highest_100[index][0]
        upto += w
    assert False, "Shouldn't get here"

def noisy_query_prediction(sessions, background_set):
    highest_100, noise_freq = count_query_frequency(background_set)
    for session in sessions:
        # for each entry in the training, val and test set insert noisy query at random position
        random_place = np.random.randint(0,len(session))
        noise = get_random_noise(highest_100, noise_freq)
        # probability of sampling a noisy query is proportional to frequency of query in background set
        session[random_place] = noise
    noisy_sessions = sessions
    return noisy_sessions

# Do LambdaMart for 3 different scenario's
# 1 Next-QueryPrediction (when anchor query exists in background data)
# for each session:

experiment_string = "next_query"
data_next_query, corresponding_queries = next_query_prediction(sessions, experiment_string)

# 2 RobustPrediction (when the context is perturbed with overly common queries)
# label 100 most frequent queries in the background set as noisy

# for i,session in enumerate(sessions):
#     if i == 0:
#         background_set = session
#     background_set += session

# experiment_string = "noisy"
# noisy_query_sessions = noisy_query_prediction(sessions, background_set)
# data_noisy, corresponding_queries = next_query_prediction(noisy_query_sessions, experiment_string)

# 3 Long-TailPrediction (when the anchor is not present in the background data)
# train, val and test set retain sessions for which the anchor query has not been
# seen in the background set (long-tail query)

# experiment_string = "long_tail"
# data_long_tail = make_long_tail_set(sessions, background_set, experiment_string)
