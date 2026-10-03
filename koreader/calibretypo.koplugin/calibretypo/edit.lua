local md5 = require("ffi/sha2").md5

local Edit = {}

local function newUid(selection, replacement)
    -- tostring({}) is unique per call, so same-second duplicates get different ids
    return md5(table.concat({
        tostring(os.time()), tostring({}), tostring(math.random()),
        selection.text, replacement,
    }, "|"))
end

function Edit.new(selection, replacement, book)
    return {
        uid = newUid(selection, replacement),
        created_at = os.date("!%Y-%m-%dT%H:%M:%SZ"),
        title = book.title,
        authors = book.authors,
        identifiers = book.identifiers,
        filename = book.filename,
        xpointer = type(selection.pos0) == "string" and selection.pos0 or nil,
        original = selection.text,
        replacement = replacement,
        context_before = selection.before,
        context_after = selection.after,
    }
end

return Edit
