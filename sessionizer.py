'''
How to use this script:
1. Set the data path to the path where your preprocessed files are.
2. Run the script from the command line: python sessionizer.py -n 10  if you want to preprocess all files. Default is the first two files
'''


class Sessionizer(object):

    def __init__(self, data_path="../data/tr_session.ctx"):
        self.data_path = data_path

    def get_sessions(self):
        sessions = []
        with open(self.data_path) as f:
            for line in f:
                sessions.append(line.rstrip('\n').split('\t'))
        return sessions
