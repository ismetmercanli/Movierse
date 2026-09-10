"""
Manuel olarak film verilerini veritabanına ekle
API key sorunu olduğunda kullanılabilir
"""

from core_services import PostgresClient, configure_windows_console

# Popüler filmler - Manuel veriler
POPULAR_MOVIES = [
    {
        'title': 'The Shawshank Redemption',
        'genre': 'Drama',
        'year': 1994,
        'rating': 9.3,
        'description': 'Two imprisoned men bond over a number of years, finding solace and eventual redemption through acts of common decency.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BNDE3ODcxYzMtY2YzZC00NmNlLWJiNDMtZDViZWM2MzIxZDYwXkEyXkFqcGdeQXVyNjAwNDUxODI@._V1_SX300.jpg'
    },
    {
        'title': 'The Godfather',
        'genre': 'Crime',
        'year': 1972,
        'rating': 9.2,
        'description': 'The aging patriarch of an organized crime dynasty transfers control of his clandestine empire to his reluctant son.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BM2MyNjYxNmUtYTAwNi00MTYxLWJmNWYtYzZlODY3ZTk3OTFlXkEyXkFqcGdeQXVyNzkwMjQ5NzM@._V1_SX300.jpg'
    },
    {
        'title': 'The Dark Knight',
        'genre': 'Action',
        'year': 2008,
        'rating': 9.0,
        'description': 'When the menace known as the Joker wreaks havoc and chaos on the people of Gotham, Batman must accept one of the greatest psychological and physical tests of his ability to fight injustice.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMTMxNTMwODM0NF5BMl5BanBnXkFtZTcwODAyMTk2Mw@@._V1_SX300.jpg'
    },
    {
        'title': 'Pulp Fiction',
        'genre': 'Crime',
        'year': 1994,
        'rating': 8.9,
        'description': 'The lives of two mob hitmen, a boxer, a gangster and his wife, and a pair of diner bandits intertwine in four tales of violence and redemption.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BNGNhMDIzZTUtNTBlZi00MTRlLWFjM2ItYzViMjE3Yz5bYWJjXkEyXkFqcGdeQXVyNzkwMjQ5NzM@._V1_SX300.jpg'
    },
    {
        'title': 'Forrest Gump',
        'genre': 'Drama',
        'year': 1994,
        'rating': 8.8,
        'description': 'The presidencies of Kennedy and Johnson, the events of Vietnam, Watergate, and other historical events unfold from the perspective of an Alabama man with an IQ of 75.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BNWIwODRlZTUtY2U3ZS00Yzg1LWJhNzYtMmZiYmEyNmU1NjMzXkEyXkFqcGdeQXVyMTQxNzMzNDI@._V1_SX300.jpg'
    },
    {
        'title': 'Inception',
        'genre': 'Sci-Fi',
        'year': 2010,
        'rating': 8.8,
        'description': 'A thief who steals corporate secrets through the use of dream-sharing technology is given the inverse task of planting an idea into the mind of a C.E.O.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMjAxMzY3NjcxNF5BMl5BanBnXkFtZTcwNTI5OTM0Mw@@._V1_SX300.jpg'
    },
    {
        'title': 'The Matrix',
        'genre': 'Sci-Fi',
        'year': 1999,
        'rating': 8.7,
        'description': 'A computer hacker learns from mysterious rebels about the true nature of his reality and his role in the war against its controllers.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BNzQzOTk3OTAtNDQ0Zi00ZTVkLWI0MTEtMDllZjNkYzNjNTc4L2ltYWdlXkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg'
    },
    {
        'title': 'Goodfellas',
        'genre': 'Crime',
        'year': 1990,
        'rating': 8.7,
        'description': 'The story of Henry Hill and his life in the mob, covering his relationship with his wife Karen Hill and his mob partners.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BY2NkZjEzMDgtN2RjYy00YzM1LWI4ZmQtMjIwYjFjNmI3ZGEwXkEyXkFqcGdeQXVyNzkwMjQ5NzM@._V1_SX300.jpg'
    },
    {
        'title': 'Star Wars',
        'genre': 'Sci-Fi',
        'year': 1977,
        'rating': 8.6,
        'description': 'Luke Skywalker joins forces with a Jedi Knight, a cocky pilot, a Wookiee and two droids to save the galaxy from the Empire\'s world-destroying battle station.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BNzVlY2MwMjktM2E4OS00Y2Y3LWE3ZjctYzhkZGM3YzA1ZWM2XkEyXkFqcGdeQXVyNzkwMjQ5NzM@._V1_SX300.jpg'
    },
    {
        'title': 'Fight Club',
        'genre': 'Drama',
        'year': 1999,
        'rating': 8.8,
        'description': 'An insomniac office worker and a devil-may-care soapmaker form an underground fight club that evolves into something much, much more.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMmEzNTkxYjQtZTc0MC00YTVjLTg5ZTEtZWMwOWVlYzY0NWIwXkEyXkFqcGdeQXVyNzkwMjQ5NzM@._V1_SX300.jpg'
    },
    {
        'title': 'Interstellar',
        'genre': 'Sci-Fi',
        'year': 2014,
        'rating': 8.6,
        'description': 'A team of explorers travel through a wormhole in space in an attempt to ensure humanity\'s survival.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BZjdkOTU3MDktN2IxOS00OGEyLWFmMjktY2FiMmZkNWIyODZiXkEyXkFqcGdeQXVyMTMxODk2OTU@._V1_SX300.jpg'
    },
    {
        'title': 'The Silence of the Lambs',
        'genre': 'Thriller',
        'year': 1991,
        'rating': 8.6,
        'description': 'A young F.B.I. cadet must receive the help of an incarcerated and manipulative cannibal killer to help catch another serial killer.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BNjNhZTk0ZmEtNjJhMi00YzFlLWE1MmEtYzM1M2ZmMGMwMTU4XkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg'
    },
    {
        'title': 'Saving Private Ryan',
        'genre': 'War',
        'year': 1998,
        'rating': 8.6,
        'description': 'Following the Normandy Landings, a group of U.S. soldiers go behind enemy lines to retrieve a paratrooper whose brothers have been killed in action.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BZjhkMDM4MWItZTVjOC00ZDRhLThmYTAtM2I5NzBmNmNlMzI1XkEyXkFqcGdeQXVyNDYyMDk5MTU@._V1_SX300.jpg'
    },
    {
        'title': 'Schindler\'s List',
        'genre': 'Drama',
        'year': 1993,
        'rating': 8.9,
        'description': 'In German-occupied Poland during World War II, industrialist Oskar Schindler gradually becomes concerned for his Jewish workforce after witnessing their persecution.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BNDE4OTMxMTctNmRhYy00NWE2LTg3YzItYTk3M2UwOTU5Njg4XkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg'
    },
    {
        'title': 'Se7en',
        'genre': 'Crime',
        'year': 1995,
        'rating': 8.6,
        'description': 'Two detectives, a rookie and a veteran, hunt a serial killer who uses the seven deadly sins as his motives.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BOTUwODM5MTctZjczMi00OTk4LTg3N2EtMTZkY2I4YjAxNDkyXkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg'
    },
    {
        'title': 'The Green Mile',
        'genre': 'Drama',
        'year': 1999,
        'rating': 8.6,
        'description': 'The lives of guards on Death Row are affected by one of their charges: a black man accused of child murder and rape, yet who has a mysterious gift.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMTUxMzQyNjA5MF5BMl5BanBnXkFtZTYwOTU2NTY3._V1_SX300.jpg'
    },
    {
        'title': 'The Usual Suspects',
        'genre': 'Crime',
        'year': 1995,
        'rating': 8.5,
        'description': 'A sole survivor tells of the twisty events leading up to a horrific gun battle on a boat, which began when five criminals met at a seemingly random police lineup.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BYTViNjMyNmUtNDFkNC00ZDRlLThmMDUtZDU2YWE4NGI2ZjVmXkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg'
    },
    {
        'title': 'Leon: The Professional',
        'genre': 'Action',
        'year': 1994,
        'rating': 8.5,
        'description': 'Mathilda, a 12-year-old girl, is reluctantly taken in by Léon, a professional assassin, after her family is murdered.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BODllNWE0MmEtYjUwZi00ZjY3LThmNmQtZjZlMjI2YTZjYmQ0XkEyXkFqcGdeQXVyNTc1NTQxODI@._V1_SX300.jpg'
    },
    {
        'title': 'The Prestige',
        'genre': 'Drama',
        'year': 2006,
        'rating': 8.5,
        'description': 'After a tragic accident, two stage magicians engage in a battle to create the ultimate illusion while sacrificing everything they have to outwit each other.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMjA4NDI0MTIxNF5BMl5BanBnXkFtZTYwNTM0MzY2._V1_SX300.jpg'
    },
    {
        'title': 'Gladiator',
        'genre': 'Action',
        'year': 2000,
        'rating': 8.5,
        'description': 'A former Roman General sets out to exact vengeance against the corrupt emperor who murdered his family and sent him into slavery.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMDliMmNhNDEtODUyOS00MjNlLTgxODEtN2U3NzIxMGVkZTA1L2ltYWdlXkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg'
    },
    {
        'title': 'The Departed',
        'genre': 'Crime',
        'year': 2006,
        'rating': 8.5,
        'description': 'An undercover cop and a mole in the police attempt to identify each other while infiltrating an Irish gang in South Boston.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMTI1MTY2OTIxNV5BMl5BanBnXkFtZTYwNjM4NjY3._V1_SX300.jpg'
    },
    {
        'title': 'The Lion King',
        'genre': 'Animation',
        'year': 1994,
        'rating': 8.5,
        'description': 'Lion prince Simba and his father are targeted by his bitter uncle, who wants to ascend the throne himself.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BYTYxNGMyZTYtMjE3MS00MzYyLWI0ZTYtYTJiYzNkMjZmMGE2XkEyXkFqcGdeQXVyNjY5NDU4NzI@._V1_SX300.jpg'
    },
    {
        'title': 'Terminator 2: Judgment Day',
        'genre': 'Sci-Fi',
        'year': 1991,
        'rating': 8.5,
        'description': 'A cyborg, identical to the one who failed to kill Sarah Connor, must now protect her ten-year-old son John from a more advanced and powerful cyborg.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMGU2NzRmZjUtOGUxYS00ZjdjLWEwZWItY2VlM2Y3MDhhMzc3XkEyXkFqcGdeQXVyNDYyMDk5MTU@._V1_SX300.jpg'
    },
    {
        'title': 'Back to the Future',
        'genre': 'Sci-Fi',
        'year': 1985,
        'rating': 8.5,
        'description': 'Marty McFly, a 17-year-old high school student, is accidentally sent thirty years into the past in a time-traveling DeLorean invented by his close friend, the maverick Doc Brown.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BZmU0M2Y1OGUtZjIxNi00ZjBkLTg1MjgtOWIyNThiZWIwYjRiXkEyXkFqcGdeQXVyMTQxNzMzNDI@._V1_SX300.jpg'
    },
    {
        'title': 'The Avengers',
        'genre': 'Action',
        'year': 2012,
        'rating': 8.0,
        'description': 'Earth\'s mightiest heroes must come together and learn to fight as a team if they are going to stop the mischievous Loki and his alien army from enslaving humanity.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BNDYxNjQyMjAtNTdiOS00NGYwLWFmNTAtNThmYjU5ZGI2YTI1XkEyXkFqcGdeQXVyMTMxODk2OTU@._V1_SX300.jpg'
    },
    {
        'title': 'Titanic',
        'genre': 'Romance',
        'year': 1997,
        'rating': 7.9,
        'description': 'A seventeen-year-old aristocrat falls in love with a kind but poor artist aboard the luxurious, ill-fated R.M.S. Titanic.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMDdmZGU3NDQtY2E5My00ZTliLWIzOTUtMTY4ZGI1YjdiNjk3XkEyXkFqcGdeQXVyNTA4NzY1MzY@._V1_SX300.jpg'
    },
    {
        'title': 'Avatar',
        'genre': 'Sci-Fi',
        'year': 2009,
        'rating': 7.9,
        'description': 'A paraplegic Marine dispatched to the moon Pandora on a unique mission becomes torn between following his orders and protecting the world he feels is his home.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BZDA0OGQxNTItMDZkMC00N2UyLTg3MzMtYTJmNjg3N2RkNGUyXkEyXkFqcGdeQXVyMjUzOTY1NTc@._V1_SX300.jpg'
    },
    {
        'title': 'Jurassic Park',
        'genre': 'Adventure',
        'year': 1993,
        'rating': 8.1,
        'description': 'A pragmatic paleontologist visiting an almost complete theme park is tasked with protecting a couple of kids after a power failure causes the park\'s cloned dinosaurs to run loose.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMjM2MDgxMDg0Nl5BMl5BanBnXkFtZTgwNTM2OTM5NDE@._V1_SX300.jpg'
    },
    {
        'title': 'The Dark Knight Rises',
        'genre': 'Action',
        'year': 2012,
        'rating': 8.4,
        'description': 'Eight years after the Joker\'s reign of anarchy, Batman, with the help of the enigmatic Catwoman, is forced from his exile to save Gotham City from the brutal guerrilla terrorist Bane.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMTk4ODQzNDY3Ml5BMl5BanBnXkFtZTcwODA0NTM4Nw@@._V1_SX300.jpg'
    },
    {
        'title': 'Iron Man',
        'genre': 'Action',
        'year': 2008,
        'rating': 7.9,
        'description': 'After being held captive in an Afghan cave, billionaire engineer Tony Stark creates a unique weaponized suit of armor to fight evil.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMTczNTI2ODUwOF5BMl5BanBnXkFtZTcwMTU0NTIzMw@@._V1_SX300.jpg'
    },
    {
        'title': 'Toy Story',
        'genre': 'Animation',
        'year': 1995,
        'rating': 8.3,
        'description': 'A cowboy doll is profoundly threatened and jealous when a new spaceman figure supplants him as top toy in a boy\'s room.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMDU2ZWJlMjktMTRhMy00ZTA5LWEzNDgtYmNmZWEwMzQxZTYxXkEyXkFqcGdeQXVyNTA4NzY1MzY@._V1_SX300.jpg'
    },
    {
        'title': 'Finding Nemo',
        'genre': 'Animation',
        'year': 2003,
        'rating': 8.2,
        'description': 'After his son is captured in the Great Barrier Reef and taken to Sydney, a timid clownfish sets out on a journey to bring him home.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BZmYxZjg3OWEtNzg5Yi00M2YzLWI1YzYtYTQ0NTgwN2ZjNjJmXkEyXkFqcGdeQXVyNDUyOTg3Njg@._V1_SX300.jpg'
    },
    {
        'title': 'The Incredibles',
        'genre': 'Animation',
        'year': 2004,
        'rating': 8.0,
        'description': 'A family of undercover superheroes, while trying to live the quiet suburban life, are forced into action to save the world.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMTY5OTU0OTc2NV5BMl5BanBnXkFtZTcwMzU4MDcyMQ@@._V1_SX300.jpg'
    },
    {
        'title': 'Up',
        'genre': 'Animation',
        'year': 2009,
        'rating': 8.3,
        'description': '78-year-old Carl Fredricksen travels to Paradise Falls in his house equipped with balloons, inadvertently taking a young stowaway.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMTk3NDE2NzI4NF5BMl5BanBnXkFtZTgwNzE1MzEyMTE@._V1_SX300.jpg'
    },
    {
        'title': 'WALL-E',
        'genre': 'Animation',
        'year': 2008,
        'rating': 8.4,
        'description': 'In the distant future, a small waste-collecting robot inadvertently embarks on a space journey that will ultimately decide the fate of mankind.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMjExMTg5OTU0NF5BMl5BanBnXkFtZTcwMjMxMzMzMw@@._V1_SX300.jpg'
    },
    {
        'title': 'The Shining',
        'genre': 'Horror',
        'year': 1980,
        'rating': 8.4,
        'description': 'A family heads to an isolated hotel for the winter where a sinister presence influences the father into violence, while his psychic son sees horrific forebodings from both past and future.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BZWFlYmY2MGEtZjVkYS00YzU4LTg0YjQtYzY1ZGE3NTA5NGQxXkEyXkFqcGdeQXVyMTQxNzMzNDI@._V1_SX300.jpg'
    },
    {
        'title': 'Alien',
        'genre': 'Horror',
        'year': 1979,
        'rating': 8.5,
        'description': 'The crew of a commercial spacecraft encounter a deadly lifeform after investigating an unknown transmission.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BOGQzZTBjMjQtOTVmMC00YGE4LWEyYmUtOGFhOGRjN2YxYzYxXkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg'
    },
    {
        'title': 'Blade Runner',
        'genre': 'Sci-Fi',
        'year': 1982,
        'rating': 8.1,
        'description': 'A blade runner must pursue and terminate four replicants who stole a ship in space and have returned to Earth to find their creator.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BNzQzMzJhZTEtOWM4NS00MTdhLTg0YjgtMjM4YWRkYWEwYzZlXkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg'
    },
    {
        'title': '2001: A Space Odyssey',
        'genre': 'Sci-Fi',
        'year': 1968,
        'rating': 8.3,
        'description': 'Humanity finds a mysterious object buried beneath the Lunar surface and sets off to find its origins with the help of HAL 9000, the world\'s most advanced super computer.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMmNlYzRiNDctZWNhMi00MzI4LThkZTctMTUzMmZkMmFmNThmXkEyXkFqcGdeQXVyNzkwMjQ5NzM@._V1_SX300.jpg'
    },
    {
        'title': 'Apocalypse Now',
        'genre': 'War',
        'year': 1979,
        'rating': 8.4,
        'description': 'A U.S. Army officer serving in Vietnam is tasked with assassinating a renegade Special Forces Colonel who sees himself as a god.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BYmQyNTA1ZTItNjMzMC00NjY4LWI4YzUtNTljM2YxMTI2ODRkXkEyXkFqcGdeQXVyNzkwMjQ5NzM@._V1_SX300.jpg'
    },
    {
        'title': 'Casino Royale',
        'genre': 'Action',
        'year': 2006,
        'rating': 8.0,
        'description': 'After earning 00 status and a licence to kill, Secret Agent James Bond sets out on his first mission as 007.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMDI5ZWJhOWItYTlhOC00YWNhLTlkNzctNDU5YTI1M2E1MWZhXkEyXkFqcGdeQXVyNTIzOTk5ODM@._V1_SX300.jpg'
    },
    {
        'title': 'Skyfall',
        'genre': 'Action',
        'year': 2012,
        'rating': 7.8,
        'description': 'James Bond\'s loyalty to M is tested when her past comes back to haunt her. When MI6 comes under attack, 007 must track down and destroy the threat, no matter how personal the cost.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMjIyOTg3OTk5NF5BMl5BanBnXkFtZTcwMTk0MjQ3OA@@._V1_SX300.jpg'
    },
    {
        'title': 'Mad Max: Fury Road',
        'genre': 'Action',
        'year': 2015,
        'rating': 8.1,
        'description': 'In a post-apocalyptic wasteland, Max teams up with a mysterious woman, Furiousa, to escape from a tyrannical warlord.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BN2EwM2I5OWMtMGQyMi00Zjg1LWJkNTctZTdjYjgyMDE0ZWI0XkEyXkFqcGdeQXVyNjU0OTQ0OTY@._V1_SX300.jpg'
    },
    {
        'title': 'Django Unchained',
        'genre': 'Western',
        'year': 2012,
        'rating': 8.4,
        'description': 'With the help of a German bounty hunter, a freed slave sets out to rescue his wife from a brutal Mississippi plantation owner.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BMjIyNTQ5NjQ1OV5BMl5BanBnXkFtZTcwODg1MDU4OA@@._V1_SX300.jpg'
    },
    {
        'title': 'Inglourious Basterds',
        'genre': 'War',
        'year': 2009,
        'rating': 8.3,
        'description': 'In Nazi-occupied France during World War II, a plan to assassinate Nazi leaders by a group of Jewish U.S. soldiers coincides with a theatre owner\'s vengeful plans for the same.',
        'poster_url': 'https://m.media-amazon.com/images/M/MV5BOTJiNDEzOWYtMTVjOC00ZjlmLWE0NGMtZmE1OWVmZDQ2ODE4XkEyXkFqcGdeQXVyNTIzOTk5ODM@._V1_SX300.jpg'
    }
]

class ManualMovieImporter:
    def __init__(self) -> None:
        self.db_client = PostgresClient()

    def run(self) -> None:
        print("=" * 70)
        print("POPULER FILMLERI MANUEL OLARAK VERITABANINA EKLEME")
        print("=" * 70)
        print()

        print("Veritabani baglantisi kuruluyor...")
        conn = self.db_client.connect()
        if not conn:
            print("HATA: Veritabani baglantisi kurulamadi!")
            input("\nDevam etmek icin Enter'a basin...")
            return

        print("Veritabani baglantisi basarili!")
        print()
        print("=" * 70)
        print(f"Toplam {len(POPULAR_MOVIES)} film islenecek...")
        print("=" * 70)
        print()

        cursor = conn.cursor()
        added_count = 0
        skipped_count = 0

        for i, movie_data in enumerate(POPULAR_MOVIES, 1):
            title = movie_data["title"]
            print(f"[{i}/{len(POPULAR_MOVIES)}] {title}...", end=" ")

            if self.db_client.movie_exists(cursor, title):
                print("ZATEN MEVCUT (atlandi)")
                skipped_count += 1
                continue

            try:
                self.db_client.add_movie(cursor, movie_data)
                conn.commit()
                print(f"EKLENDI [OK] (IMDb: {movie_data['rating']})")
                added_count += 1
            except Exception as exc:
                conn.rollback()
                print(f"HATA: {exc}")

        conn.close()

        print()
        print("=" * 70)
        print("ISLEM TAMAMLANDI!")
        print("=" * 70)
        print(f"Eklenen: {added_count}")
        print(f"Atlanan (zaten mevcut): {skipped_count}")
        print(f"Toplam: {len(POPULAR_MOVIES)}")
        print("=" * 70)
        print()
        input("Devam etmek icin Enter'a basin...")


if __name__ == "__main__":
    configure_windows_console()
    ManualMovieImporter().run()

