from bs4 import BeautifulSoup
import requests
import praw
import sqlite3
from pathlib import Path
import re
import random
import logging
import time

#Initialize a logging object and have some examples below from the Python Doc page
logging.basicConfig(filename='AFILinkerBot.log',level=logging.INFO)

logging.info(time.strftime("%Y/%m/%d %H:%M:%S ") + "Starting script")

#reddit user object
creds = open('LinkerBotCreds.txt', 'r')
credsUserAgent = creds.readline()
credsClientID = creds.readline()
credsClientSecret = creds.readline()
credsUsername = creds.readline()
credsPassword = creds.readline()
creds.close()
reddit = praw.Reddit(user_agent=credsUserAgent.strip(), client_id=credsClientID.strip(), client_secret=credsClientSecret.strip(), username=credsUsername.strip(), password=credsPassword.strip())

#regex expression used to search for an AFI mention
AFIsearchRegEx = "((afi|afpd|afman|afva|afh|afji|afjman|afpam|afgm|afpci|aetci|usafai|afttp)[0-9]{1,2}-[0-9]{1,4}([0-9]{1})?([a-z]{1,2}-)?([0-9]{1,3})?(vol|v)?\d?)|((af|form|afform|sf|afto|afcomsec|afg|apda|aftd|imt|afimt|aetc)[0-9]{1,4}([a-z]{1,3})?)"

#Reply templates to go in the middle of comments
NormalReplyTemplate = '^^It ^^looks ^^like ^^you ^^mentioned ^^an ^^AFI, ^^form ^^or ^^other ^^publication, ^^so ^^I ^^have ^^posted ^^a ^^link ^^to ^^it. ^^Additionally, ^^there ^^may ^^be ^^other ^^MAJCOM, ^^NAF ^^or ^^Wing ^^sups ^^to ^^the ^^linked ^^AFI, ^^so ^^I ^^will ^^also ^^post ^^a ^^link ^^to ^^the ^^search ^^URL ^^used ^^below ^^so ^^that ^^you ^^can ^^see ^^look ^^for ^^additional ^^supplements ^^or ^^guidance ^^memos ^^that ^^may ^^apply. ^^Please ^^let ^^me ^^know ^^if ^^this ^^is ^^incorrect ^^or ^^if ^^you ^^have ^^a ^^suggestion ^^to ^^make ^^me ^^better ^^by ^^posting ^^in ^^my ^^subreddit ^^(/r/AFILinkerBot).\n\n'
SmarmyReplyTemplate = 'This is where I would normally post a link to an AFI or something but I see you tried to reference an AFTTP. So instead I will leave you a gem from /r/AirForce, chosen at random from a list:\n\n'

conn = ""
dbCommentRecord = ""
globalCount = 0
dbFile = Path("CommentRecord.db")
#check to see if database file exists
if dbFile.is_file():
	#connection to database file
	conn = sqlite3.connect("CommentRecord.db")
	#database cursor object
	dbCommentRecord = conn.cursor()
else: #if it doesn't, create it
	conn = sqlite3.connect("CommentRecord.db")
	dbCommentRecord = conn.cursor()
	dbCommentRecord.execute('''CREATE TABLE comments(comment text)''')


#subreddit instance of /r/AirForce. 'AFILinkerBot' must be changed to 'airforce' for a production version of the script. AFILB subreddit used for testing
subreddit = 'AFILinkerBot'
rAirForce = reddit.subreddit(subreddit)

logging.info(time.strftime("%Y/%m/%d %H:%M:%S ") + "Starting processing loop for subreddit: " + subreddit)

while True:
	try:
		#stream all comments from /r/AirForce
		for rAirForceComments in rAirForce.stream.comments():
			globalCount += 1
			print("\nComments processed since start of script: " + str(globalCount))
			print("Processing comment: " + rAirForceComments.id)

			#prints a link to the comment. A True for permalinnk generates a fast find (but is not an accurate link, just makes the script faster *SIGNIFICANTLY FASTER)
			permlink = "http://www.reddit.com" + rAirForceComments.permalink(True) + "/"
			print(permlink)
			logging.info(time.strftime("%Y/%m/%d %H:%M:%S ") + "Processing comment: " + permlink)

			#Pulls all comments previously commented on
			dbCommentRecord.execute("SELECT * FROM comments WHERE comment=?", (rAirForceComments.id,))

			id_exists = dbCommentRecord.fetchone()

			#Make sure we don't reply to the same comment twice or to the bot itself
			if id_exists:
				print("Already processed comment: " + str(rAirForceComments.id) + ", skipping")
				continue
			elif(rAirForceComments.author == "AFILinkerBot"):
				print("Author was the bot, skipping...")
				continue
			else:
				#make the comment all lowercase and remove all spaces, change vol to v, and other cleanup
				formattedComment = rAirForceComments.body
				formattedComment = formattedComment.lower()
				formattedComment = formattedComment.replace(' ', '')
				if "afform" in formattedComment:
						formattedComment = formattedComment.replace('form', '')
				if "aftoform" in formattedComment:
					formattedComment = formattedComment.replace('form', '')
				if "form" in formattedComment:
						formattedComment = formattedComment.replace('form', 'af')
				formattedComment = formattedComment.replace('vol','v')
				print("Formatted Comment: " + formattedComment)

				#search the comments for a match
				inputToTest = re.compile(AFIsearchRegEx, re.IGNORECASE)
				MatchedComments = inputToTest.finditer(formattedComment)

				#Keep a list of matched comments so we only post one link per AFI
				ListOfMatchedComments = []

				#Variables to hold all the matched AFI links and their respective search links
				TotalAFILinks = ""
				TotalSearchLinks = ""

				#Iterate through all the matched oomments
				for individualMention in MatchedComments:
					#Skip to the next match if an AFI referenced has already been processed. Prevents post multiple links to the same pub
					if individualMention.group() in ListOfMatchedComments:
						continue
					else:
						#Add the matched comment into the master list
						ListOfMatchedComments.append(individualMention.group())

						# searchLink is what is posted at the bottom of the comment to let people search for their own crap
						searchLink = '[' + str(individualMention.group()).upper() + ' search link](http://www.e-publishing.af.mil/index.asp?txtSearchWord=%s&btnG.x=28&btnG.y=4&client=AFPW_EPubs&proxystylesheet=AFPW_EPubs&ie=UTF-8&oe=UTF-8&output=xml_no_dtd&site=AFPW_EPubs)' % individualMention.group()

						#polls the epubs website for a search
						epubsReturn = requests.get('http://www.e-publishing.af.mil/shared/resource/EPubLibraryV3/EPubLibrary.aspx?type=Pubs&search_title=%s' % individualMention.group())
						epubsSearch = BeautifulSoup(epubsReturn.text, 'html.parser')

						#A little extra something
						if "afttp" in individualMention.group():
							dalist = []
							with open('smarmycomments.txt', 'r') as f:
								dalist = f.read().splitlines()
							print("Dropping a smarmy comment on the mention of: " + individualMention.group() + " by " + str(rAirForceComments.author) + ". Comment ID: " + rAirForceComments.id)
							logging.info(time.strftime("%Y/%m/%d %H:%M:%S ") + "Dropping a smarmy comment on the mention of: " + individualMention.group() + " by " + str(rAirForceComments.author) + ". Comment ID: " + rAirForceComments.id + "\n")
							rAirForceComments.reply(SmarmyReplyTemplate + (dalist[random.randint(0, len(dalist) - 1)]))
							dbCommentRecord.execute('INSERT INTO comments VALUES (?);', (rAirForceComments.id,))
							conn.commit()
							continue

						#regex to match exactly the afi typed from the ePubs crawl
						individualMentionRegex = "(?<=/)(" + individualMention.group() + ")(?=\.pdf)"
						#scrub the epubs search return and look for an exact match between a / and .pdf
						epubsSearchForAllLinesWithPDF = epubsSearch.find_all(string=re.compile(individualMentionRegex))

						#Parse through anything returned and start building the TotalAFILinks and TotalSearchLinks variables
						for link in epubsSearchForAllLinesWithPDF:
							print("Link: " + link)
							TotalAFILinks += link + "\n\n"
							TotalSearchLinks += searchLink + "\n\n"

				#if the TotalAFILinks variable isn't empty (no matches), prepare the reply comment
				if TotalAFILinks != "":
					replyComment = TotalAFILinks
					replyComment += "___________________________________________________________\n\n"
					replyComment += NormalReplyTemplate
					replyComment += "___________________________________________________________\n\n"
					replyComment += "\n\n" + TotalSearchLinks
					# create db record of comment so we don't comment on it again
					dbCommentRecord.execute('INSERT INTO comments VALUES (?);', (rAirForceComments.id,))

					# Comments on post
					print("Commenting on mention of: " + str(ListOfMatchedComments) + " by " + str(rAirForceComments.author) + ". Comment ID: " + rAirForceComments.id)
					logging.info(time.strftime("%Y/%m/%d %H:%M:%S ") + "Commenting on mention of: " + str(ListOfMatchedComments) + " by " + str(rAirForceComments.author) + ". Comment ID: " + rAirForceComments.id + "\n")
					# Comments on post
					rAirForceComments.reply(replyComment)
					# save changes to db
					conn.commit()

	#what to do if Ctrl-C is pressed while script is running
	except KeyboardInterrupt:
		print ("Keyboard Interrupt/Ctrl-c experienced, cleaning up and exiting")
		conn.commit()
		conn.close()
		print ("Exiting due to keyboard interrupt")
		logging.info(time.strftime("%Y/%m/%d %H:%M:%S ") + "Exiting due to keyboard interrupt")
		exit()