import praw
import json
import html
import yaml
import logging

logging.basicConfig(level=logging.DEBUG)
r = None

def try_reddit_action(action):
    value = None
    try:
        value = action()
    except Exception as e:
        logging.error('ERROR: {0}'.format(e))
        raise
    return value

def initialize():
    global r
    stream = open('settings.yaml', 'r')
    settings = yaml.load(stream)
    stream.close()
    
    username = settings['username']
    password = settings['password']
    user_agent = '%s - Config Updater' % username
    r = praw.Reddit(user_agent=user_agent)
    r.login(username, password)

def accept_invites(subreddit_invites):
    for subreddit in subreddit_invites:
        try:
            r.accept_moderator_invite(subreddit)
            logging.info('Accepted mod invite in /r/{0}'.format(subreddit))
        except praw.errors.InvalidInvite:
            pass
    
def update_config(update_request_messages):
    global r

    for author, body in update_request_messages:
        config = yaml.load(body)
        source_sub = config['source']
        logging.info('Getting text from source sub: %s' % source_sub)
        source_subreddit = r.get_subreddit(source_sub)
        source_page = try_reddit_action(lambda: source_subreddit.get_wiki_page(config['text_page']))
        source_text = source_page.content_md
        logging.info('Source: %s' % source_text)
        settings_page = try_reddit_action(lambda: source_subreddit.get_wiki_page(config['settings_page']))
        settings = settings_page.content_md
        
        for setting in yaml.load_all(settings):
            logging.info('Replacing template with source text for sub %s' % setting['destination_sub'])
            destination_subreddit = r.get_subreddit(setting['destination_sub'])
            if (author not in [i.name for i in destination_subreddit.get_moderators()]):
                logging.info('Message author %s not a mod in destination subreddit %s' % (author, setting['destination_sub']))
                continue
            
            destination_template = setting['template']
            destination_text = destination_template.replace('{{text}}', source_text)
            destination_text = html.unescape(destination_text)

            if (config['update'] == 'description'):
                logging.info('Saving updated template')
                try_reddit_action(lambda: destination_subreddit.update_settings(description=destination_text))

            if (config['update'].startswith('wiki')):
                wikipage = config['update'].split('.')[1]
                destination_page = try_reddit_action(lambda: destination_subreddit.get_wiki_page(wikipage))
                try_reddit_action(lambda: destination_page.edit(destination_text))
    
from datetime import datetime
import os
from apscheduler.schedulers.blocking import BlockingScheduler

def tick():
    global r
    try_reddit_action(initialize)
    messages = try_reddit_action(lambda: r.get_unread(limit = None))
    subreddit_invites = set()
    update_request_messages = set()
    
    for message in messages:
        if message.was_comment:
            continue

        # if it's a subreddit invite
        if (not message.author and
                message.subject.startswith('invitation to moderate /r/')):
            subreddit_invites.add(message.subreddit.display_name.lower())
        elif message.subject.strip().lower() == 'update':
            update_request_messages.add((message.author.name, message.body))
        r.user.mark_as_read(message)
        
    accept_invites(subreddit_invites)
    update_config(update_request_messages)

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(tick, 'interval', seconds=60)
    logging.info('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        pass
