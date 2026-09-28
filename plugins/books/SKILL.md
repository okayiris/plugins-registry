---
name: books
description: The owner's reading list through the books plugin, kept in its own database: books to read, reading now and read, with stars from 1 to 5 and notes, and books looked up on Open Library.
whenToUse: When the owner wants to remember a book to read, says they started or finished one, asks what they are reading or read this year, wants a thought kept with a book, or asks who wrote a book or how long it is.
---

# books

```sh
books                               # reading now, and the size of the lists
books find project hail mary        # Open Library: title, author, year, pages
books want project hail mary        # the best match onto the to-read list
books start hail mary               # by title or by #id
books done hail mary 4              # finished, four stars
books note 3 "The ending!"
books show 3
books list want                     # or reading, read, or all three
books year 2026
books drop 3
```

- `want`, `start` and `done` take the best Open Library match; when the title is common, check with
  `books find` first and include the author in the words.
- Ask before `books drop`: it forgets the notes too.
