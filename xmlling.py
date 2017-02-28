import pickle 




# print(doc)
from lxml import etree

node = [n for n,d in tree.in_degree().items() if d==0][0]
node.xml = etree.Element('span', **{'class':node.name}, start=str(node.start), end = str(node.end))
root = node
stack = [node]
while stack:
    node = stack.pop(0)

    children = tree.successors(node)
    if children:
        cs = sorted(children, key=lambda x:x.start)
        for idx, child in enumerate(cs):
            child.xml = etree.Element('span', **{'class':child.name}, start=str(child.start), end = str(child.end))
            try:
                if child.end < cs[idx + 1].start:
                    child.xml.tail = text[child.end:cs[idx + 1].start]
            except IndexError:
                pass

            node.xml.append(
                child.xml
            )
            stack.append(child)
    else:
        pass
        node.xml.text = text[node.start:node.end]



document = etree.Element('span', **{'class':'document'},
                         start=str(0), end = str(len(text)))
document.text = (
    text[:int(root.start)]
)
document.append(root.xml)

t = text[int(root.end):]

END = root.end


root.xml.tail = t

f = open('index.html', 'w')

f.write('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Title</title>
    <link rel="stylesheet" type="text/css" href="main.css">

</head>
<body>
{}
</body>
</html>'''.format(
etree.tostring(document, pretty_print=True, encoding='utf8').decode('utf8')))
