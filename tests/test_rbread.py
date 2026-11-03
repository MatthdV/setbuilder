from types import SimpleNamespace as NS

from setbuilder.rbread import Track, map_content, read_library


def test_map_content_minimal():
    row = NS(ID=7, BPM=12800, KeyName="Cm")
    t = map_content(row)
    assert isinstance(t, Track)
    assert t.content_id == "7"
    assert t.bpm == 128.0
    assert t.rb_key == "Cm"
    assert t.camelot == "5A"
    assert t.moment is None and t.ambiance is None
    assert t.duration_s is None
    assert t.title is None and t.file_path is None
    assert t.has_cues == 0 and t.has_phrases == 0


def test_map_content_empty_row_does_not_raise():
    t = map_content(NS(ID=1))
    assert t.bpm is None and t.camelot is None and t.rb_key is None


def test_map_content_full():
    tag = lambda name, cat: NS(MyTag=NS(Name=name, Parent=NS(Name=cat)))
    row = NS(
        ID=42, Title="Song", ArtistName="Artist", AlbumName="Album",
        GenreName="House", BPM=12450, Key=NS(ScaleName="Abm"),
        Length=301, FolderPath="/music/song.mp3",
        Cues=[NS(), NS()],
        MyTags=[tag("Peak", "Moment"), tag("Dark", "Ambiance")],
    )
    t = map_content(row)
    assert (t.title, t.artist, t.album, t.genre) == ("Song", "Artist", "Album", "House")
    assert t.bpm == 124.5
    assert (t.rb_key, t.camelot) == ("Abm", "1A")
    assert (t.moment, t.ambiance) == ("Peak", "Dark")
    assert t.duration_s == 301
    assert t.file_path == "/music/song.mp3"
    assert t.has_cues == 1


def test_read_library_iterates_db():
    db = NS(get_content=lambda: [NS(ID=1), NS(ID=2)])
    assert [t.content_id for t in read_library(db)] == ["1", "2"]
