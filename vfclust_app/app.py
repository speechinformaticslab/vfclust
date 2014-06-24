import os
from traceback import format_exc

import flask, flask.views

from VFClust_phon import PVF

app = flask.Flask(__name__)

app.secret_key= "secrets"

class View(flask.views.MethodView):
    def get(self):
        return flask.render_template('index.html')

    def post(self):
        try:
            arg1=flask.request.form['Letterbox']
            arg2=flask.request.form['Comma_Separted_String_Box']
            calltomodule=PVF(arg1, arg2)
            #flask.flash(calltomodule.response)
            flask.flash(calltomodule.display)
            return self.get()
        except:
            flask.flash("Error: Invalid input. Please try again using only comma separated words in the text box.")
            return self.get()
            
        
      


app.add_url_rule('/vf-clust', view_func=View.as_view('main'), methods=['GET', 'POST'])


if __name__ == '__main__':
    app.run()
