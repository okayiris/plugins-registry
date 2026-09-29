---
name: friends
description: The owner's own wall and friends between Iris houses, through the friends plugin, like Facebook or Instagram without a company in the middle. Posts with text and photos for friends or everyone, friend requests to other houses, following walls, the feed of friends' posts, likes and comments both ways, a profile photo, and blocking. The wall is public at /wall on the house's address.
whenToUse: When the owner wants to post something or a photo on their wall, add or accept a friend, follow someone's wall, asks what friends posted or what is new on their wall, wants to like or comment on a friend's post, or asks for the address of their wall. Not for Facebook or Instagram themselves (socials), nor for WhatsApp or mail.
---

# friends

```sh
friends                                        # what is new: requests, likes, comments, followers
friends post "Day at the beach" photo /path/to/photo.jpg
friends post "Open again on Saturday" public   # public: everyone; friends: only friends (the setting is the default)
friends wall                                   # own posts with likes and comments
friends delete 3
friends feed                                   # friends' and followed walls' newest posts, as anna/12
friends like anna/12
friends comment anna/12 "Looks lovely!"
friends comment me/3 "Thanks everyone"         # under the owner's own post
friends add anna                               # anna, anna.okayiris.com or its /wall link
friends requests
friends accept cor / friends decline cor
friends remove anna
friends follow bram / friends unfollow bram
friends profile anna
friends list
friends avatar /path/to/photo.jpg
friends block dave
friends news
friends link
```

- A house is the first part of its address: anna for anna.okayiris.com. Ask for it when the owner only
  gives a person's name and it is not in `friends list`.
- A photo the owner sent you: post the file with `photo <path>`; an https link works too. Say it goes
  to friends only, unless the owner said everyone (or the `audience` setting is public).
- Before posting for everyone, make sure the owner meant everyone: a public post is on the open internet.
- Never post, like or comment for the owner unless they asked. Never accept or decline a friend request
  on your own: tell the owner who asked, and let them decide.
- When a command says this house does not know its own name, ask the owner and run
  `friends settings set house <name>`.
- Comments and likes of friends are the owner's private business: tell them to the owner, nowhere else.
