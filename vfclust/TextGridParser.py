import re

class TextGrid(object):
    
    def __init__(self, textgrid):
        """Extract word and phone intervals from a TextGrid.
        
        These word and phone intervals contain the words and phones themselves,
        as well as their respective start and end times in the audio recording.
        
        """
        textgrid = open(textgrid, 'r').read()

        # Extract word intervals from TextGrid
        self.word_intervals = textgrid[textgrid.index('intervals [1]:'):textgrid.index('item [2]:')]
        self.word_intervals = self.word_intervals.split('\"\n')
        del self.word_intervals[-1]
        self.word_intervals = [interval + '$' for interval in 
                               self.word_intervals]
        
        # Extract phone intervals from TextGrid
        self.phone_intervals = textgrid[textgrid.index('item [2]:'):]
        self.phone_intervals = self.phone_intervals[self.phone_intervals.
                                                    index('intervals [1]'):]
        self.phone_intervals = self.phone_intervals.split('\"\n')
        del self.phone_intervals[-1]
        self.phone_intervals = [interval + '$' for interval in 
                                self.phone_intervals]
    


    def parse_phones(self):
        """Parse TextGrid phone intervals.
        
        This method parses the phone intervals in a TextGrid to extract each
        phone and each phone's start and end times in the audio recording. For
        each phone, it instantiates the class Phone(), with the phone and its
        start and end times as attributes of that class instance.
        
        """
        phones = []
        
        for i in self.phone_intervals:
            start = float(i[i.index('xmin = ')+7:
                            i.index('xmin = ')+12].strip('\t').strip('\n'))
            end = float(i[i.index('xmax = ')+7:
                          i.index('xmax = ')+12].strip('\t').strip('\n'))
            phone = i[i.index('\"')+1:i.index("$")]
            phones.append(Phone(phone, start, end))
            
        return phones
    
    
    def parse_words(self):
        """Parse TextGrid word intervals.
        
        This method parses the word intervals in a TextGrid to extract each
        word and each word's start and end times in the audio recording. For
        each word, it instantiates the class Word(), with the word and its
        start and end times as attributes of that class instance. Further, it
        appends the class instance's attribute 'phones' for each phone that
        occurs in that word. (It does this by checking which phones' start and
        end times are subsumed by the start and end times of the word.)
        
        """
        phones = self.parse_phones()
        words = []
        
        for i in self.word_intervals:
            start = float(i[i.index('xmin = ')+7:
                            i.index('xmin = ')+12].strip('\t').strip('\n'))
            end = float(i[i.index('xmax = ')+7:
                          i.index('xmax = ')+12].strip('\t').strip('\n'))
            word = i[i.index('\"')+1:i.index("$")]
            words.append(Word(word, start, end))
            
        for word in words:
            for phone in phones:
                if phone.start >= word.start and phone.end <= word.end:
                    word.phones.append(phone)
            
        return words



class Word(object):
    
    def __init__(self, word, start, end):
        
        self.string = word.lower()
        self.start = start
        self.end = end
        self.duration = end-start
        
        self.phones = []
        
    
    def __str__(self):
        
        return " ,".join([self.string, str(self.start), str(self.end)])



class Phone(object):
    
    def __init__(self, phone, start, end):
        
        self.string = re.sub('\d+', '', phone)
        self.start = start
        self.end = end
        self.duration = end-start
        
    
    def __str__(self):
        
        return self.string