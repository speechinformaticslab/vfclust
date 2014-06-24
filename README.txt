VFClust
=======

This package is designed to generate clustering analyses for
transcriptions of semantic and phonemic verbal fluency test responses.
In a verbal fluency test, the subject is given a set amount of time
(usually 60 seconds) to name as many words as he or she can that
correspond to a given specification. For a phonemic test, subjects are
asked to name words that begin with a specific letter. For a semantic
fluency test, subjects are asked to provide words of a certain category,
e.g. animals. VFClust groups words in responses based on phonemic or
semantic similarity, as described below. It then calculates metrics
derived from the discovered groups and returns them as a CSV file or
Python dict.

Verbal fluency tests are often used in test batteries used to study
cognitive impairment arising from e.g. Alzheimer's disease, Parkinson's
disease, and certain medications.

More here on scientific background for clustering...

Mayr, U. (2002). On the dissociation between clustering and switching in
verbal fluency: Comment on Troyer, Moscovitch, Winocur, Alexander and
Stuss. Neuropsychologia, 40(5), 562-566.

Ryan et al., Computerized Analysis of a Verbal Fluency Test
http://rxinformatics.umn.edu/downloads/VFCLUST/ryan\_acl2013.pdf

Clustering in VFClust
---------------------

VFClust finds adjacent subsets of words of the following types:

-  clusters: every entry in a cluster is sufficiently similar to every
   other entry

-  chains: every entry in a chain is sufficiently similar to adjacent
   entries

where "entry" corresponds to a word, compound word, or multiple adjacent
words with the same stem.

Similarity scores between words are thresholded and binarized using
empirically-derived thresholds. Overlap of clusters is allowed (a word
can be part of multiple clusters), but overlapping chains are not
possible, as any two adjacent words with a lower-than-threshold
similarity breaks the chain. Clusters subsumed by other clusters are not
counted.

The similarity measures used are the following:

-  PHONETIC/"phone": the phonetic similarity score (PSS) is calculated
   between the phonetic representations of the input units. It is equal
   to 1 minus the Levenshtein distance between two strings, normalized
   to the length of the longer string. The strings should be compact
   phonetic representations of the two words. (This method is a
   modification of a Levenshtein distance function available at
   http://hetland.org/coding/python/levenshtein.py.)

-  PHONETIC/"biphone": the binary common-biphone score (CBS) depends on
   whether two words share their initial and/or final biphone (i.e., set
   of two phonemes). A score of 1 indicates that two words have the same
   intial and/or final biphone; a score of 0 indicates that two words
   have neither the same initial nor final biphone This is also
   calculated using the phonetic representation of the two words.

-  SEMANTIC/"lsa": a semantic relatedness score (SRS) is calculated as
   the COSINE of the respective term vectors for the first and second
   word in an LSA space of the specified clustering\_parameter. Unlike
   the PHONETIC methods, this method uses the .text property of the
   input Unit objects.

Output
~~~~~~

After chains/clusters are discovered using the methods relevant for the
type of fluency test performed, metrics are derived from the clusters
and output to screen and a .csv file (if run as a script) or to a python
dict object (if run as a package). The following metrics are calculated:

Counts of different token types in the raw input. Each of these is
prefaced by ''COUNT\_'' in the output.

-  total\_words: count of words (i.e. utterances with semantic content)
   spoken by the subject. Filled pauses, silences, coughs, breaths,
   words by the interviewer, etc. are all excluded from this count.

-  permissible\_words: Number of words spoken by the subject that
   qualify as a valid response according to the clustering criteria.
   Compound words are counted as a single word in SEMANTIC clustering,
   but as two words in PHONETIC clustering.

-  exact\_repetitions: Number of words which repeat words spoken earlier
   in the response. Responses in SEMANTIC clustering are lemmatized
   before this function is called, so slight variations (dog, dogs) may
   be counted as exact responses.

-  stem\_repetitions: Number of words stems identical to words uttered
   earlier in the response, according to the Porter Stemmer. For
   example, 'sled' and 'sledding' have the same stem ('sled'), and
   'sledding' would be counted as a stem repetition.

-  examiner\_words: Number of words uttered by the examiner. These start
   with "E\_" in .TextGrid files.

-  filled\_pauses: Number of filled pauses uttered by the subject. These
   begin with "FILLEDPAUSE\_" in the .TextGrid file.

-  word\_fragments: Number of word fragments uttered by the subject.
   These end with "-" in the .TextGrid file.

-  asides: Words spoken by the subject that do not adhere to the test
   criteria are counted as asides, i.e. words that do not start with the
   appropriate letter or that do not represent an animal.

-  unique\_permissible\_words: Number of works spoken by the subject,
   less asides, stem repetitions and exact repetitions.

Measures derived from clusters/chains in the response. Each of these is
prefaced by ''COLLECTION\_'', along with the similarity measure used and
the collection type the measure was calculated over.

-  pairwise\_similarity\_score\_mean: mean of pairwise similarity
   scores. The pairwise similarity is calculated as the sum of
   similarity scores for all pairwise word pairs in a response -- except
   any pair composed of a word and itself -- divided by the total number
   of words in an attempt. I.e., the mean similarity for all pairwise
   word pairs.

-  count: number of collections

-  size\_mean: mean size of collections

-  size\_max: size of largest collection

-  switch\_count: number of changes between clusters

Measures derived from timing information in the response, along with
clusters/chains. Each of these is prefaced by ''TIMING\_'' along with
the along with the similarity measure used and the collection type the
measure was calculated over.

-  response\_vowel\_duration\_mean: average vowel duration of all vowels
   in the response.-

-  response\_continuant\_duration\_mean: average vowel duration of all
   vowels in the response.

-  between\_collection\_interval\_duration\_mean: average interval
   duration separating clusters. Negative intervals (for overlapping
   clusters) are counted as 0 seconds. Intervals are calculated as being
   the difference between the ending time of the last word in a
   collection and the start time of the first word in the subsequent
   collection. Note that these intervals are not necessarily silences,
   and may include asides, filled pauses, words from the examiner, etc.

-  within\_collection\_interval\_duration\_mean: the mean time between
   the end of each word in the collection and the beginning of the next
   word. Note that these times do not necessarily reflect pauses, as
   collection members could be separated by asides or other noises.

-  within\_collection\_vowel\_duration\_mean: average duration of vowels
   that occur within a collection

-  within\_collection\_continuant\_duration\_mean: average duration of
   continuants that occur within a collection.

Project Setup
-------------

To install the package, download the zip file, and extract it. In the
terminal, navigate to the location of the unzipped package and type

::

    python setup.py install

You will need to have the gcc compiler installed on your system.
Installing also includes compiling a C executable for the
grapheme-to-phoneme conversion (t2p) that the phonetic clustering
package uses. If everything went okay, you should see the following
output in the console:

::

    success S AH0 K S EH1 S

along with other output from the install process.

Check that the package is installed by starting Python and typing:

::

    import vfclust

You can also check that the script runs by changing to the vfclust
subdirectory and running:

::

    python vfclust.py ../example/EXAMPLE.TextGrid -p s

This runs VFClust on a phonemic fluency test response using the letter
's' on the EXAMPLE.TextGrid file provided.

Dependencies
~~~~~~~~~~~~

This package has been tested on Mac OS X (Mavericks). In order to run
the package you must have the following installed on your machine:

0. Python 2.7

1. **NLTK**: VFClust requires the Natural Language Toolkit (NLTK), as it
   uses the NLTK lemmatizer and stemmer in parsing subject responses.
   Check http://www.nltk.org for more information on how to install
   NLTK.

2. **pip**: To install pip from any computer that already has Python 2.7
   installed, go to your terminal or commandline of choice and enter the
   command below:

   easy\_install pip

3. **gcc**: On Mac OS X, you will need to install the latest version of
   Xcode compatible with your version of OS X with Command-line tools
   package (https://developer.apple.com/xcode/). Keep in mind that you
   may need to enable command-line tools in Xcode in order to be able to
   use the gcc compiler. If you can't run gcc from command-line after
   installing Xcode, go to the Xcode Preferences/Downloads tab and
   select the "Install" button, next to "Command Line Tools."

Testing
-------

*How do I run the project's automated tests?*

Deploying
---------

*Input*
~~~~~~~

VFClust operations are performed on transcriptions of

*As a script*
~~~~~~~~~~~~~

Navigate to the directory containing the vfclust.py file (it should be
in the vfclust/ subdirectory) and type:

::

    vfclust.py [-h] [-s SEMANTIC] [-p PHONEMIC] [-o OUTPUT_PATH] [-q] source_file_path

Bracketed arguments are optional, but either -s (semantic) or -p
(phonemic) must be selected. The arguments are as follows:

positional arguments: source\_file\_path Full path of textgrid or csv
file to parse

optional arguments:

::

    -h, --help      show this help message and exit

    -s SEMANTIC     Usage: -s animals If included, calculates measures for the
                    given category for the semantic fluency test, i.e.
                    animals, fruits, etc.

    -p PHONEMIC     Usage: -p f If included, calculates measures for the given
                    category for the phonemic fluency test, i.e. a, f, s, etc.

    -o OUTPUT_PATH  Where to put output - default is the same directory as the
                    input file working directory.

    -q              Use to eliminate output to screen (default is print everything to
                    stdout).

*As a Python package*
~~~~~~~~~~~~~~~~~~~~~

Contributing changes
--------------------

-  *Internal git workflow*
-  *Pull request guidelines*
-  *Tracker project*
-  *Google group*
-  *irc channel*
-  *"Please open github issues"*

ACKNOWLEDGEMENTS
----------------

This package uses a grapheme-to-phoneme conversion (t2p) implementation
by the MBRDICO Project (http://tcts.fpms.ac.be/synthesis/mbrdico/).

The English Open Word List is used as a basic dictionary of English
words. http://dreamsteep.com/projects/the-english-open-word-list.html

License
-------

All files which are included as a part of the VFClust Phonetic
Clustering Module are provided under an Apache license, excluding:

-  t2p.c in the src directory, which is provided under a GPL license,
   and

-  english\_words.txt in the data/EOWL directory, which is a
   modification of the UK Advanced Cryptics Dictionary and is released
   with the following licensing:

Copyright  J Ross Beresford 1993-1999. All Rights Reserved. The
following restriction is placed on the use of this publication: if the
UK Advanced Cryptics Dictionary is used in a software package or
redistributed in any form, the copyright notice must be prominently
displayed and the text of this document must be included verbatim.
