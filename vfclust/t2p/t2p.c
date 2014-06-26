#define VERSION "0.5"

char ProgInfo[]=
"* $Id: run_tree.c,v 1.1.1.1 2002/03/07 16:48:14 pagel Exp $\n"
"* Purpose: parse and run a decision tree          \n"
"* Author: Vincent Pagel ( pagel@tcts.fpms.ac.be ) \n"
"* Version : " VERSION  "\n"
"* Time-stamp: <2002-02-22 14:30:50 pagel>                          \n"
"*                                                 \n"
"* Copyright (c) 1998 Faculte Polytechnique de Mons (TCTS lab) \n"
"* Copyright (c) 2001-2002 Multitel asbl\n"
"*                                                             \n"
"* This program is free software; you can redistribute it and/or modify \n"
"* it under the terms of the GNU General Public License as published by \n"
"* the Free Software Foundation version 1 \n"
"* \n"
"* This program is distributed in the hope that it will be useful, \n"
"* but WITHOUT ANY WARRANTY; without even the implied warranty of \n"
"* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the \n"
"* GNU General Public License for more details. \n"
"* \n"
"* You should have received a copy of the GNU General Public License \n"
"* along with this program; if not, write to the Free Software \n"
"* Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA. \n"
"* \n"
"* History: \n"
"* \n"
"*  12/08/98 : Created. To parse and run a decision tree in a .tree \n"
"*  file, whose structure is:                                   \n"
"*            SWITCH : '[' attrib  default_value CASE+ ']' \n"
"*            CASE   : feature SWITCH |  feature value          \n"
"*                                                              \n"
"*  attrib: [0..9]+  (index of the feature to test)             \n"
"*  feature: string                                             \n"
"*  val and default_value: string (phoneme)                     \n"
"*                                                              \n"
"*  17/08/98 : added a specific node counter, and change the method so that we\n"
"*      consider a big if_then_else in with each if count for 1, as well as each \n"
"*      return \n"
"*\n"
"*  16/05/99 : more explicit debug mode\n"
"*  21/06/99 : left to right transcription direction\n"
"*  28/11/01 : boundary character was chosen really badly, now use a '~'\n"
"*             the format of the tree change a little bit\n"
"*\n"
"*\n"
"*\n"
"*/\n";

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <unistd.h>
#include <stdarg.h>

/* Related to choices in conv2vec !!! */
/* #define TEXT_BOUNDARY "~" */

#define TEXT_BOUNDARY "-"
#define PHONEME_BOUNDARY "-"
#define PHONEME_EPSILON "_"

typedef char* Phoneme;
typedef char* Feature;
typedef Feature* TestVector;

/* Switch-case-default statement ! */
typedef struct 
{
  int feature_index;  /* index of the feature to carry the tests on */

  int nb_case;    /* number of cases available */
  struct Case ** cases;    /* table of case pointers */

  Phoneme default_phoneme; /* default return value */
} Switch;
#define feature_index(S) (S->feature_index)
#define nb_case(S) (S->nb_case)
#define cases(S) (S->cases)
#define default_phoneme(S) (S->default_phoneme)

enum 
{
  Terminal,							  /* Terminal node */
  Recursive							  /* Recursive node */
} TypeNode;

/* Case statement */
typedef struct Case
{
  Feature feature;    /* value of the tested feature */
  int type;          /* Terminal node or not */
  
  union 
  {
	 Switch* decision;  /* Embedded decision */
	 Phoneme return_phoneme;     /* or return value */
  } u;
} Case;
#define feature(C) (C->feature)
#define type(C)    (C->type)
#define decision(C)  (C->u.decision)
#define return_phoneme(C) (C->u.return_phoneme)

/*
 * Global variable
 */
int max_depth; /* volontary limit the depth of search in the tree */

int modulo; /* to print something each nth test */
int trace;  /* if true, display the decision path */
int transcribe;  /* Don't compute alignement statistics, simply phonetize */

/* Attribute parsing in the file */
int  left_grapheme=0;
int  right_grapheme=0;
int  nb_feedback=0;
int  nb_skip=0;
int left_to_right;


/* 
 * Here we go ....
 */

void tabulate(int depth)
	  /* print the right number of space to justify the ouput */
{
  int i;
  
  for(i=0; i<depth; i++)
	 fprintf(stdout,"  ");
}

void display_debug(int index)
	  /* print the origin of a vector's element (trace purpose) */
{
  if (index < nb_skip)
    fprintf(stdout,"TAG%i",index);
  else if (index < left_grapheme+right_grapheme+1 + nb_skip)
    fprintf(stdout,"L%i",index - left_grapheme - nb_skip);
  else 
    fprintf(stdout,"P-%i",index - left_grapheme - right_grapheme - nb_skip);
}


Case* init_Case()
	  /* Alloc memory */
{
  Case* my_case= (Case*) malloc(sizeof(Case));

  return(my_case);
}

void close_Switch(Switch* sw);
/* Release the memory */

void close_Case(Case* cs)
	  /* Release the momory */
{
  free(feature(cs));
  switch (type(cs))
	 {
	 case Recursive:
		close_Switch(decision(cs));
		break;

	 case Terminal:
		free(return_phoneme(cs));
		break;

	 default:
		fprintf(stderr,"Unknown node type %i\n",type(cs));
		exit(1);
	 }
  
  free(cs);
}

void print_Switch(Switch* sw, int depth);

void print_Case(Case* cs,int depth)
{
  tabulate(depth);  
  fprintf(stdout," case %s:\n", feature(cs));

  switch (type(cs))
	 {
	 case Recursive:
		print_Switch( decision(cs), depth+1);
		break;
		
	 case Terminal:
		tabulate(depth);  
		fprintf(stdout,"  return %s\n",return_phoneme(cs));
		break;
		
	 default:
		fprintf(stderr,"Unknown node type %i\n",type(cs));
		exit(1);
	 }
}

int count_Switch(Switch* sw, int depth);

int count_Case(Case* cs, int depth)
	  /* node counter */
{
  int count=0;
  
  switch (type(cs))
	 {
	 case Recursive:
		count+= count_Switch( decision(cs), depth+1);
		break;
		
	 case Terminal:
		count=1;
		break;
		
	 default:
		fprintf(stderr,"Unknown node type %i\n",type(cs));
		exit(1);
	 }  
  return(count);
}


Switch* parse_Switch(FILE* decision_file);
/* parse a Switch statement in the decision file */


Case* parse_Case(FILE* decision_file,char* token)
	  /* Parse a Case statement in the decision file */
{
  Case* my_case=init_Case();
  char value[255];
  
  feature(my_case)= strdup(token);
  
  fscanf(decision_file," %s ",value);
  if (strcmp(value,"[")==0)
	 {
		/* This is a recursive Switch bloc */
		type(my_case)=Recursive;
		decision(my_case)= parse_Switch(decision_file);
	 }
  else
	 {
		/* This is a terminal node */
		type(my_case)=Terminal;
		return_phoneme(my_case)= strdup(value);
	 }
  return(my_case);
}

Phoneme run_Switch(Switch* sw, TestVector vector, int depth);
/* recursively run the decision tree */

Phoneme run_Case(Case* cs, TestVector vector, int depth)
	  /* Run the decision tree */
{
  if (type(cs)==Terminal)
	 {
		if (trace)
		  fprintf(stdout," -> %s\n", return_phoneme(cs));
		return return_phoneme(cs) ;
	 }
  
  else
	 return run_Switch( decision(cs), vector, depth+1);
}


Switch* init_Switch()
{
  Switch* my_switch= (Switch*) malloc( sizeof(Switch) );

  nb_case(my_switch)=0;
  cases(my_switch)=NULL;
  default_phoneme(my_switch)=NULL;
  feature_index(my_switch)=-1;
  return(my_switch);
}

void close_Switch(Switch* sw)
	  /* Release the memory */
{
  int i;
  
  for(i=0; i<nb_case(sw); i++)
	 close_Case( cases(sw)[i] );

  if (default_phoneme(sw))
	 free(default_phoneme(sw));
  
  free(sw);
}

void print_Switch(Switch* sw, int depth)
{
  int i;
  
  tabulate(depth);  
  fprintf(stdout,"switch (%i) {\n", feature_index(sw));

  tabulate(depth);  
  fprintf(stdout,"/* %i %i %i */\n", feature_index(sw),depth,nb_case(sw));

  if (depth>=max_depth)
	 { /* well do go deeper and print the default value */
	 } 
  else
	 {
		for(i=0; i<nb_case(sw); i++)
		  print_Case(cases(sw)[i], depth);
	 }
  
  tabulate(depth);  
  fprintf(stdout," default: return %s\n",default_phoneme(sw));
  tabulate(depth);  
  fprintf(stdout,"}\n");
}

int count_Switch(Switch* sw, int depth)
	  /* node counter */
{
  int i;
  int count=1; /* one for the default return */
  
  if (depth>=max_depth)
	 {
		/* nothing ! */
	 } 
  else
	 {
		for(i=0; i<nb_case(sw); i++)
		  count+= 1 + count_Case(cases(sw)[i], depth); /* one for each condition */
	 }
  return(count);
}

/* A a new case statement to a Switch structure */
void addcase_Switch(Switch* my_switch,Case* my_case)
{
  /* make some room, somehow ugly ! -> if sorted insertion, dichotomic search later :-) */
  cases(my_switch)=(Case**) realloc(cases(my_switch), 
				    sizeof(Case*) * (nb_case(my_switch)+1) );
  cases(my_switch)[nb_case(my_switch)]=my_case;
  
  nb_case(my_switch)++;
}

/* parse a Switch statement in the decision file */
Switch* parse_Switch(FILE* decision_file)
{
  char token[255];
  Switch* my_switch=init_Switch();
  
  if ( fscanf(decision_file," %i ",& feature_index(my_switch)) != 1)
    {
      fprintf(stderr,"Lack FEATURE_INDEX\n");
      exit(1);
    }
  
  fscanf(decision_file," %s ",token);
  default_phoneme(my_switch)=strdup(token);
  
  do
    {
      fscanf(decision_file," %s ",token);
      
      if (strcmp(token,"]")==0)
	{
	  break;  /* leave the level */
	}
      else
	{
	  /* The token was a feature */
	  Case* my_case=parse_Case(decision_file,token);
	  addcase_Switch(my_switch,my_case);
	}
    } while (1);
  
  return(my_switch);
}

void parse_vector_format(char* line)
	  /* format of the learning vector */
{
  int position=0;
  int  nb_LRfeedback=0;
  int  nb_RLfeedback=0;

  while ( line[position]!=0 )
	 {
		switch (line[position]) 
		  {
		  case 'L':
			 left_grapheme++; 
			 break;
			 
		  case 'R':
			 right_grapheme++;
			 break;
			 
		  case 'T': /* target, ignore for the moment. It's mostly visual */
			 break;
			 
		  case 'P':
			 nb_RLfeedback++;
			 break;

		  case 'Q':
			 nb_LRfeedback++;
			 break;
		 
		  case 'S':
			 nb_skip++;
			 break;

		  case ' ':	  /*  Ignore blanks */
		  case 10:
		  case 12:
		  case 13:
			 break;
			
		  default:
			 fprintf(stderr,"unknown attrib *%c*\n",line[position]);
			 exit(1);
			 break;
		  }
		position++;
	 }

  /* Those flags are incompatible */
  if (nb_RLfeedback*nb_LRfeedback!=0)
	 {
		fprintf(stderr,"Can't apply LEFT and RIGHT feedback at the same time\n");
		exit(-1);
	 }

  /* Decide the feedback direction */
  if (nb_RLfeedback>nb_LRfeedback)
	 {
		left_to_right=0;
		nb_feedback=nb_RLfeedback;
	 }
  else
	 {
		left_to_right=1;
		nb_feedback=nb_LRfeedback;
	 }
}

Switch* read_Switch(char* decision_name)
	  /* Read the tree file */
{
  FILE* decision_file;
  Switch* my_decision;
  int position=0;
  char line[1024];
  
  decision_file=fopen(decision_name,"rt");
  if (!decision_file)
	 {
		fprintf(stderr,"FATAL Error, can't open %s\n",decision_name);
		exit(1);
	 }

  fgets(line, sizeof(line), decision_file);
  if ( strncmp(line, "ID3" VERSION ,6) != 0)
    {
      fprintf(stderr,"ID3" VERSION " is not compatible with format: %s", line);
      exit(1);
    }
  
  /* Skip copyright notice */
  do
    {
      fgets(line,sizeof(line),decision_file);
    }
  while (line[0]=='#');
  
  /* Read the format of the learning vector */
  parse_vector_format(line);

  /* Eat the opening braket */
  fscanf(decision_file," [ %n",&position);

  if (position!=0)
	 my_decision=parse_Switch(decision_file);
  else
	 {
		fprintf(stderr,"Lack [\n");
		exit(1);
	 }
  return(my_decision);
}

Phoneme run_Switch(Switch* sw, TestVector vector, int depth)
	  /* Run the decision tree */
{
  int i;
  
  if (depth<max_depth)
    {
      /* Linear search in the cases... may be dichotomic later ? */
      for(i=0; i<nb_case(sw); i++)
	{
	  if (strcmp( feature(cases(sw)[i]) , vector[feature_index(sw)]) ==0)
	    {
	      if (trace)
		{ 
		  fprintf(stdout,"(%s) ",default_phoneme(sw));
		  
		  display_debug( feature_index(sw) );
		  fprintf(stdout,"=%s ",vector[feature_index(sw)]);
		}
	      return( run_Case( cases(sw)[i], vector, depth) );
	    }
	}
    }
  /* default case */
  if (trace)
    {
      fprintf(stdout,"(%s) ",default_phoneme(sw));
      display_debug( feature_index(sw) );
      fprintf(stdout,"=%s default-> (%s)\n", vector[feature_index(sw)], default_phoneme(sw));
    }
  return( default_phoneme(sw) );
}

/* Transcribe a serie of words */
void Evaluation(FILE* test_file, Switch* decision)
{
  int nb_word=0;
  int nb_word_success=0;
  int nb_phone=0;
  int nb_phone_success=0;
  double stat;
  char original_line[1024];

  while (fgets(original_line,sizeof(original_line), test_file))
    {
      char* solution[100]; /* Solution of the dictionnary */
      int nb_solution=0;   /* number of elements in the solution */
      
      char str_solution[255]="";
      char str_phoneme[255]="";
      
      char* phoneme[100];    /* Computed solution, including trailing '-' */
      int nb_phoneme=0;
      
      char* guess[100];    /* Computed solution */
      
      char* grapheme[100]; /* graphemic feature, including leading and trailing '-' */
      int nb_grapheme;

      char* skip[100]; /* Part of speech features */
      
      char* word; /* word to transcribe */
      Feature vector[100];
      int index=1; /* because 1st was phoneme during training */
      
      char temp[1024];
      char line[1024];
      int j,i;

      strcpy(line,original_line);
      
      /* First come the word graphemic */
      word= strtok(line," \n\r");
      if (!word)
	break; /* empty line */
      
      /* Eventually build extra feature list */
      for (j=0; j<nb_skip; j++)
	skip[j]= strtok(NULL," \n\r");

      /*
       * Build Solution (phonemic transcription)
       */
      while ( (solution[nb_solution++]=strtok(NULL," \n\r")) != NULL)
	{/* empty */
	}
      nb_solution--; /* the last one was NULL */
		
      /*
       * Build Grapheme
       */
      for(j=0; j<left_grapheme; j++)
	grapheme[j]= strdup(TEXT_BOUNDARY);
      
      temp[1]=0;
      
      for(nb_grapheme=0; word[nb_grapheme]!=0; nb_grapheme++,j++)
	{
	  temp[0]=word[nb_grapheme];
	  grapheme[j]=strdup(temp);
	}
      
      for(i=0 ; i<right_grapheme; i++,j++)
	grapheme[j]=strdup(TEXT_BOUNDARY);
      
      /*
       * Build Phoneme feedback trailing '-'
       */
      for (nb_phoneme=0; nb_phoneme< nb_feedback; nb_phoneme++)
	phoneme[nb_phoneme]=strdup(PHONEME_BOUNDARY);
      

      /* Sanity check */
      if ((nb_solution != nb_grapheme) &&
	  !transcribe )
	{
	  fprintf(stderr,"UNALIGNED MATERIAL:%s\n", original_line);
	  exit(1);
	}

      /* 
       * Let's transcribe each letter, from end to beginning !
       */
      
      if (left_to_right)
	{
	  int k;
	  for(k=0; k<j/2; k++) /* reverse the graphemic string */
	    {
	      char* temp= grapheme[k];
	      grapheme[k]= grapheme[j-1-k];
	      grapheme[j-1-k]= temp;
	    }
	  for(k=0; k<nb_solution/2; k++) /* reverse the phonemic solution */
	    {
	      char* temp= solution[k];
	      solution[k]= solution[nb_solution-1-k];
	      solution[nb_solution-1-k] = temp;
	    }
	}
      
      /* MAIN ITERATION */
      for(j= nb_grapheme-1; j!=-1; j--)
	{
	  /* LLLTRRRR */
	  index= 0; 

	  /* contain external features such as PART_OF_SPEECH */
	  for(i=0; i<nb_skip; i++)
	    vector[index++]= skip[i];
	  
	  for(i=0; i< left_grapheme+right_grapheme+1; i++)
	    vector[index++]=grapheme[i+j];
	  
	  /* Phonemic loop */
	  for(i=0; i<nb_feedback; i++)
	    vector[index++]= phoneme[nb_phoneme-1-i];
	  
	  if (trace)
	    {
	      int j;
	      for(j=0;j<index;j++)
		fprintf(stdout,"%s ",vector[j]);
	      fprintf(stdout,": ");
	    }
	  
	  /* transcribe the vector ! */
	  guess[j]= run_Switch(decision,vector,0);
	  
	  /* progress if non nul transcription */
	  if (strcmp(guess[j],PHONEME_EPSILON) !=0 )
	    { 
	      phoneme[nb_phoneme++]= guess[j];
	      
	      /* build the phonemic transcription without epsilons */
	      if (left_to_right)
		{
		  strcat(str_phoneme,guess[j]);
		  strcat(str_phoneme," ");
		}
	      else
		{
		  char local[100]="";
		  sprintf(local,"%s %s",guess[j],str_phoneme);
		  strcpy(str_phoneme,local);
		}
	    }
	  
	  if (!transcribe)
	    { 
	      if (strcmp( guess[j], solution[j]) == 0 )
		nb_phone_success++;
	      
	      /* build the phonemic solution without epsilons */
	      if (strcmp(solution[j],PHONEME_EPSILON)!=0)
		{ 
		  if (left_to_right)
		    {
		      strcat(str_solution,solution[j]);
		      strcat(str_solution," ");
		    }
		  else
		    {
		      char local[100]="";
		      sprintf(local,"%s %s",solution[j],str_solution);
		      strcpy(str_solution,local);
		    }
		}
	    }
	  nb_phone++;
	}
      
      if (transcribe)
	{ /* simply report the phonetization... nothing else */
	  
	  /* Remove pseudo phonemes */
	  char*  pos= strchr(str_phoneme,'+');
	  while (pos)
	    {
	      *pos=' ';
	      pos= strchr(str_phoneme,'+');
	    }
	  
	  /* the word */
	  fprintf(stdout,"%s ",word);
	  
	  /* print the SKIP features */
	  for (j=0; j<nb_skip; j++)
	    fprintf(stdout,"%s ", vector[j]);
	  
	  /* phonetization */
	  fprintf(stdout, "%s\n", str_phoneme);
	}
      else
	{ /* Number of words correctly transcribed */
	  if (strcmp(str_solution, str_phoneme)==0)
	    {
	      nb_word_success++;
	      if ( (modulo>0) &&
		   ( (nb_word % modulo)==0))
		fprintf(stdout,"Good\n%s %s\n",word,str_solution);
	    }
	  else
	    {
	      fprintf(stdout,"Wrong\n%s ",word);
	      if (nb_skip!=0)
		fprintf(stdout,"%s ",vector[0]);
	      fprintf(stdout,"%s\n",str_phoneme);

	      fprintf(stdout,"%s ",word);
	      if (nb_skip!=0)
		fprintf(stdout,"%s ",vector[0]);
	      fprintf(stdout,"%s\n", str_solution); 
	    }
	  nb_word++;
	}
    }
  
  if (!transcribe)
    { /* print collected statistics ... */
      stat= 100.0 * (double) nb_word_success / (double)nb_word;
      fprintf(stdout,"Read %i words, %i success (%f/100) Error=%i\n",nb_word,nb_word_success,stat,nb_word-nb_word_success);
      
      stat= 100.0 * (double) nb_phone_success / (double)nb_phone;
      fprintf(stdout,"Read %i letters, %i success (%f/100)\n",nb_phone,nb_phone_success,stat);
      
      fprintf(stdout,"Nbnode=%i\n", count_Switch(decision,0));
    }
}

int main(int argc, char **argv)
{
  char* decision_name;
  char* test_name;
  FILE* test_file;
  Switch* decision;
  int argpos=1;
 
  /* Display the decision's path */
  transcribe=0;
  if ( (argc > argpos) &&
       (strcmp(argv[argpos] , "-transcribe") == 0))
    {
      argpos++;
      transcribe=1;
    }

  /* Display the decision's path */
  trace=0;
  if ( (argc > argpos) &&
       (strcmp(argv[argpos] , "-trace") == 0))
    {
      argpos++;
      trace=1;
    }

  /* Maximum depth to use in the tree */
  max_depth=32000;
  if ( (argc > argpos) &&
       (strcmp(argv[argpos] , "-depth") == 0))
    {
      argpos++;
      max_depth= atoi( argv[ argpos++ ]);
    }

  /* Modulo to print the output */
  modulo=-1;
  if ( (argc > argpos) &&
       (strcmp(argv[argpos] , "-modulo") == 0))
    {
      argpos++;
      modulo= atoi( argv[ argpos++ ]);
    }

  if (argc>argpos)
    {
      decision_name=argv[ argpos++ ];
      decision= read_Switch(decision_name);
    }
  else
    {
      fprintf(stderr,ProgInfo);
      fprintf(stderr,"USAGE: %s [-transcribe] [-trace] [-depth max] [-modulo mod] decision.tree [test|-]\n",argv[0]);
      return(1);
    }

  /* Simply print the decision tree */
  if (argc<=argpos)
    {
      print_Switch(decision,0);
      close_Switch(decision);
      return 0;
    }
  
  test_name= argv[argpos++];
  if (strcmp(test_name,"-")==0)
    {
      test_file=stdin;
    }
  else
    {
      if (!(test_file= fopen(test_name,"rt")))
	{
	  fprintf(stderr,"Can't open %s\n",test_name);
	  exit(1);
	}
    }
  
  Evaluation(test_file,decision);
  
  /* Destructor */
  close_Switch(decision);
  return 0;
}
