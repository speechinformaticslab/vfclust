__author__ = 'Tom'

import os, re, subprocess
from tempfile import NamedTemporaryFile
from vfclust import data_path, lemmatizer, stemmer, print_table


# holds sequence of adjacent words with the same stem
class Unit():
    """ Class to hold a sequence of 1 or more adjacent words with the same stem, or a compound word.

    A Unit may represent:
        - single words (dog, cat)
        - lemmatized/compound words (polar_bear)
        - several adjacent words with the same root (follow/followed/following)
     The object also includes:
        - phonetic/semantic representation of the FIRST word, if more than one
        - The start time of the first word and the ending time of the final word
    """
    def __init__(self, word, format, type, index_in_timed_response = None):
        """Initialization of Unit object.

        :param word:        Original word that the Unit represents.
        :type word:         If format is "TextGrid", this must be a TextGrid.Word object.
                            If format is "csv", this must be a string.
        :param str format:  'TextGrid' or 'csv'
        :param str type:    'SEMANTIC' or 'PHONETIC
        :param int index_in_timed_response: Index in the raw response input.
                Used to find phone-level information later if necessary.
        :rtype : Unit object
        """
        self.type = type
        self.format = format
        self.phonetic_representation = None
        self.index_in_timed_response = index_in_timed_response

        if self.format == "TextGrid":
            self.text = word.string.lower()
            self.original_text = [word.string.lower()] # list b/c there might be more than one in the future
            self.start_time = word.start
            self.end_time = word.end
            self.duration = word.duration
        elif self.format == "csv":
            self.text = word.lower()
            self.original_text = [word.lower()] # list b/c there might be more than one in the future
            self.start_time = None
            self.end_time = None
            self.duration = None

    def __str__(self):
        """ Enables the str() function. Returns the simplest textual representation of the Unit."""
        return self.text


class ParsedResponse():
    """ Implements a representation of a subject response, along with methods for parsing it.

    ParsedResponse is a list-like class that contains a list of Unit objects and properties
    relevant to type of clustering being performed by VFClust. It implements methods for
    simplifying the list of Units, removing repetitions, creating compound words, removing
    irrelevant response tokens, etc.
         """
    def __init__(self,response_type,
                 letter_or_category,
                 quiet = False,
                 cmudict = None, # dictionary of phonetic representations of words
                 english_words = None, # big list of legal words
                 lemmas = None, # list of available lemmas
                 names = None, # list of tokenized responses, i.e. tokenized animal names
                 permissible_words = None): # list of semantic words (animals, etc)

        """Initializes a ParsedResponse object.

        :param str response_type:    'PHONETIC' or 'SEMANTIC - used for determining whether
                            lemmatization/tokenization should be done during initialization
        :param str letter_or_category: letter (for type='PHONETIC') or string (for type='SEMANTIC')
                            required for determining which Units in the list are appropriate responses
                            to the current fluencyt ask
        :param bool quiet:  If True, suppresses output to screen.
        :param dict cmudict: Dictionary of phonetic representations of words. Used for phonetic clustering.
        :param list english_words: Big list of English words. Used to determine whether responses
                            in the phonetic clustering response are in English.
        :param set lemmas:  Set of available lemmas, i.e. words in their simplest version (non-plural)
        :param list names:  List of tokenized responses, i.e. compound words.
        :param list permissible_words:  List of legal words of the relevant dimension
        """
        self.type = response_type
        self.letter_or_category = letter_or_category
        self.quiet = quiet
        self.cmudict = cmudict
        self.english_words = english_words
        self.lemmas = lemmas
        self.names = names
        self.permissible_words = permissible_words

        self.unit_list = []
        self.timing_included = None

        self.iterator_index = 0 # used for iterating

    def __iter__(self):
        """
        Makes the object iterable, iterates over the list of units in the ParsedResponse.
        """
        return iter(self.unit_list)


    def __len__(self):
        """
        Implements len(), returns length of the list of units in the ParsedResponse.

        """
        return len(self.unit_list)

    def __getitem__(self,i):
        """ Implements e.g. parsed_response[i] to return the ith Unit in the ParsedResponse. """
        return self.unit_list[i]

    def create_from_csv(self,token_list):
        """ Fills the ParsedResponse object with a list of words/tokens originally from a .csv file.

        :param list token_list: List of strings corresponding to words in the subject response.

        Modifies:
            - self.timing_included: csv files do not include timing information
            - self.unit_list: fills it with Unit objects derived from the token_list argument.
                If the type is 'SEMANTIC', the words in these units are automatically lemmatized and
                made into compound words where appropriate.
        """
        self.timing_included = False
        for entry in token_list:
            self.unit_list.append(Unit(entry, format = "csv", type = self.type))

        # combine compound words, remove pluralizations, etc
        if self.type == "SEMANTIC":
            self.lemmatize()
            self.tokenize()

    def create_from_textgrid(self,word_list):
        """ Fills the ParsedResponse object with a list of TextGrid.Word objects originally from a .TextGrid file.

        :param list word_list: List of TextGrid.Word objects corresponding to words/tokens in the subject response.

        Modifies:
            - self.timing_included: TextGrid files include timing information
            - self.unit_list: fills it with Unit objects derived from the word_list argument.
                If the type is 'SEMANTIC', the words in these units are automatically lemmatized and
                made into compound words where appropriate.
        """
        self.timing_included = True
        for i, entry in enumerate(word_list):
            self.unit_list.append(Unit(entry, format="TextGrid",
                                       type=self.type,
                                       index_in_timed_response=i))

        # combine compound words, remove pluralizations, etc
        if self.type == "SEMANTIC":
            self.lemmatize()
            self.tokenize()

    def lemmatize(self):
        """Lemmatize all Units in self.unit_list.

        Modifies:
            - self.unit_list: converts the .text property into its lemmatized form.

        This method lemmatizes all inflected variants of permissible words to
        those words' respective canonical forms. This is done to ensure that
        each instance of a permissible word will correspond to a term vector with
        which semantic relatedness to other words' term vectors can be computed.
        (Term vectors were derived from a corpus in which inflected words were
        similarly lemmatized, meaning that , e.g., 'dogs' will not have a term
        vector to use for semantic relatedness computation.)
        """
        for unit in self.unit_list:
            if lemmatizer.lemmatize(unit.text) in self.lemmas:
                    unit.text = lemmatizer.lemmatize(unit.text)


    def tokenize(self):
        """Tokenizes all multiword names in the list of Units.

        Modifies:
            - (indirectly) self.unit_list, by combining words into compound words.

        This is done because many names may be composed of multiple words, e.g.,
        'grizzly bear'. In order to count the number of permissible words
        generated, and also to compute semantic relatedness between these
        multiword names and other names, multiword names must each be reduced to
        a respective single token.
        """
        if not self.quiet:
            print
            print "Finding compound words..."

        # lists of animal names containing 2-5 separate words
        compound_word_dict = {}
        for compound_length in range(5,1,-1):
            compound_word_dict[compound_length] = [name for name in self.names if len(name.split()) == compound_length]

        current_index = 0
        finished = False
        while not finished:
            for compound_length in range(5,1,-1): #[5, 4, 3, 2]
                if current_index + compound_length - 1 < len(self.unit_list): #don't want to overstep bounds of the list
                    compound_word = ""
                    #create compound word
                    for word in self.unit_list[current_index:current_index + compound_length]:
                        compound_word += " " + word.text
                    compound_word = compound_word.strip() # remove initial white space
                    #check if compound word is in list
                    if compound_word in compound_word_dict[compound_length]:
                        #if so, create the compound word
                        self.make_compound_word(start_index = current_index, how_many = compound_length)
                        current_index += 1
                        break
            else: #if no breaks for any number of words
                current_index += 1
                if current_index >= len(self.unit_list): # check here instead of at the top in case
                                                         # changing the unit list length introduces a bug
                    finished = True

    def make_compound_word(self, start_index, how_many):
        """Combines two Units in self.unit_list to make a compound word token.

        :param int start_index: Index of first Unit in self.unit_list to be combined
        :param int how_many: Index of how many Units in self.unit_list to be combined.

        Modifies:
                - self.unit_list: Modifies the Unit corresponding to the first word
                    in the compound word. Changes the .text property to include .text
                    properties from subsequent Units, separted by underscores. Modifies
                    the .original_text property to record each componentword separately.
                    Modifies the .end_time property to be the .end_time of the final unit
                    in the compound word.  Finally, after extracting the text and timing
                    information, it removes all units in the compound word except for the
                    first.

        .. note: This method is only used with semantic processing, so we don't need to worry
            about the phonetic representation of Units.

        """
        if not self.quiet:
            compound_word = ""
            for word in self.unit_list[start_index:start_index + how_many]:
                compound_word += " " + word.text
            print compound_word.strip(), "-->","_".join(compound_word.split())

        #combine text
        for other_unit in range(1, how_many):
            self.unit_list[start_index].original_text.append(self.unit_list[start_index + other_unit].text)
            self.unit_list[start_index].text += "_" + self.unit_list[start_index + other_unit].text

        #start time is the same. End time is the end time of the LAST word
        self.unit_list[start_index].end_time = self.unit_list[start_index + how_many - 1].end_time

        #shorten unit_list
        self.unit_list = self.unit_list[:start_index + 1] + self.unit_list[start_index + how_many:]

    def remove_unit(self, index):
        '''Removes the unit at the given index in self.unit_list. Does not modify any other units.'''
        if not self.quiet:
            print "Removing", self.unit_list[index].text
        self.unit_list.pop(index)

    def combine_same_stem_units(self, index):
        """Combines adjacent words with the same stem into a single unit.

        :param int index: Index of Unit in self.unit_list to be combined with the
            subsequent Unit.

        Modifies:
                - self.unit_list: Modifies the .original_text property of the Unit
                    corresponding to the index.  Changes the .end_time property to be the
                    .end_time of the next Unit, as Units with the same stem are considered
                     as single Unit inc lustering. Finally, after extracting the text and timing
                    information, it removes the unit at index+1.

        """

        if not self.quiet:
            combined_word = ""
            for word in self.unit_list[index:index + 2]:
                for original_word in word.original_text:
                    combined_word += " " + original_word
            print combined_word.strip(), "-->","/".join(combined_word.split())

        # edit word list to reflect what words are represented by this unit
        self.unit_list[index].original_text.append(self.unit_list[index + 1].text)

        #start time is the same. End time is the end time of the LAST word
        self.unit_list[index].end_time = self.unit_list[index + 1].end_time

        # remove word with duplicate stem
        self.unit_list.pop(index + 1)


    def display(self):
        """Pretty-prints the ParsedResponse to the screen."""

        table_list = []
        table_list.append(("Text","Orig. Text","Start time","End time", "Phonetic"))
        for unit in self.unit_list:
            table_list.append((unit.text,
                               "/".join(unit.original_text),
                               unit.start_time,
                               unit.end_time,
                               unit.phonetic_representation))
        print_table(table_list)

    def generate_phonetic_representation(self, word):
        """
        Returns a generated phonetic representation for a word.

        :param str word: a word to be phoneticized.
        :return: A list of phonemes representing the phoneticized word.

        This method is used for words for which there is no pronunication
        entry in the CMU dictionary. The function generates a
        pronunication for the word in the standard CMU format. This can then
        be converted to a compact phonetic representation using
        modify_phonetic_representation().

        """
        with NamedTemporaryFile() as temp_file:
            # Write the word to a temp file
            temp_file.write(word)
            #todo - clean up this messy t2p path
            t2pargs = [os.path.abspath(os.path.join(os.path.dirname(__file__),'../t2p/t2p')),
                       '-transcribe', os.path.join(data_path, 'cmudict.0.7a.tree'),
                       temp_file.name]
            temp_file.seek(0)
            output, error = subprocess.Popen(
                t2pargs, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            ).communicate()
            output = output.split()
            phonetic_representation = output[1:]

        return phonetic_representation

    def modify_phonetic_representation(self, phonetic_representation):
        """ Returns a compact phonetic representation given a CMUdict-formatted representation.

        :param list phonetic_representation: a phonetic representation in standard
            CMUdict formatting, i.e. a list of phonemes like ['HH', 'EH0', 'L', 'OW1']
        :returns: A string representing a custom phonetic representation, where each phoneme is
            mapped to a single ascii character.

        Changing the phonetic representation from a list to a string is useful for calculating phonetic
        simlarity scores.
        """

        for i in range(len(phonetic_representation)):
            # Remove numerical stress indicators
            phonetic_representation[i] = re.sub('\d+', '', phonetic_representation[i])

        multis = ['AA', 'AE', 'AH', 'AO', 'AW', 'AY', 'CH', 'DH', 'EH', 'ER',
                  'EY', 'HH', 'IH', 'IY', 'JH', 'NG', 'OW', 'OY', 'SH',
                  'TH', 'UH', 'UW', 'ZH']

        singles = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l',
                   'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w']

        for i in range(len(phonetic_representation)):
            # Convert multicharacter phone symbols to arbitrary
            # single-character symbols
            if phonetic_representation[i] in multis:
                phonetic_representation[i] = singles[multis.index(phonetic_representation[i])]
        phonetic_representation = ''.join(phonetic_representation)

        return phonetic_representation

    def clean(self):
        """ Removes any Units that are not applicable given the current semantic or phonetic category.

        Modifies:
            - self.unit_list: Removes Units from this list that do not fit into the clustering category.
                it does by by either combining units to make compound words, combining units with the
                same stem, or eliminating units altogether if they do not conform to the category.
                 If the type is phonetic, this method also generates phonetic clusters for all Unit
                 objects in self.unit_list.


        This method performs three main tasks:
            1. Removes words that do not conform to the clustering category (i.e. start with the
                wrong letter, or are not an animal).
            2. Combine adjacent words with the same stem into a single unit. The NLTK Porter Stemmer
                is used for determining whether stems are the same.
                http://www.nltk.org/_modules/nltk/stem/porter.html
            3. In the case of PHONETIC clustering, compute the phonetic representation of each unit.

        """

        if not self.quiet:
            print
            print "Preprocessing input..."
            print "Raw response:"
            print self.display()

        if not self.quiet:
            print
            print "Cleaning words..."

        #weed out words not starting with the right letter or in the right category
        current_index = 0
        while current_index < len(self.unit_list):
            word = self.unit_list[current_index].text
            if self.type == "PHONETIC":
                test = (word.startswith(self.letter_or_category) and  #starts with required letter
                        not word.endswith('-') and  # Weed out word fragments
                            '_' not in word and # Weed out, e.g., 'filledpause_um'
                        word.lower() in self.english_words) #make sure the word is english
            elif self.type == "SEMANTIC":
                test = word in self.permissible_words
            if not test: #if test fails remove word
                self.remove_unit(index = current_index)
            else: # otherwise just increment, but check to see if you're at the end of the list
                current_index += 1

        #combine words with the same stem
        current_index = 0
        finished = False
        while current_index < len(self.unit_list) - 1:
            #don't combine for lists of length 0, 1
            if stemmer.stem(self.unit_list[current_index].text) == \
                stemmer.stem(self.unit_list[current_index + 1].text):
                #if same stem as next, merge next unit with current unit
                self.combine_same_stem_units(index = current_index)
            else: # if not same stem, increment index
                current_index += 1

        #get phonetic representations
        if self.type == "PHONETIC":
            for unit in self.unit_list:
                word = unit.text

                #get phonetic representation
                if word in self.cmudict:
                    # If word in CMUdict, get its phonetic representation
                    phonetic_representation = self.cmudict[word]
                if word not in self.cmudict:
                    # Else, generate a phonetic representation for it
                    phonetic_representation = self.generate_phonetic_representation(word)
                    phonetic_representation = self.modify_phonetic_representation(phonetic_representation)

                unit.phonetic_representation = phonetic_representation

        if not self.quiet:
            print
            print "Cleaned response:"
            print self.display()


